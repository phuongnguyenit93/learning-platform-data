# Xây dựng phần tính toán thuần và giữ tác dụng phụ ở ranh giới trong Java

Một thiết kế theo hàm (*functional design*) không nhất thiết phải loại bỏ toàn bộ I/O, biến mutable hoặc ngoại lệ. Ứng dụng vẫn cần đọc tệp, gọi API, nhận thời gian hiện tại, truy vấn database và lưu kết quả. Ý tưởng quan trọng hơn là **tách phần quyết định kết quả khỏi phần tương tác với thế giới bên ngoài**: xây dựng một lõi tính toán dễ kiểm chứng, sau đó đặt việc đọc/ghi ở một số ranh giới có thể nhận diện và kiểm soát.

Cách tổ chức này thường được gọi là **functional core, imperative shell**: lõi chủ yếu xử lý đầu vào thành đầu ra, còn lớp vỏ điều phối những tác vụ có tác dụng phụ. Trong Java 17+, ta có thể áp dụng nguyên tắc bằng các phương thức thông thường, `record`, `Stream`, `List` và các interface nhỏ mà không cần framework chuyên dụng.

## 1. “Thuần” nghĩa là gì?

Một hàm thuần (*pure function*) có hai đặc tính đáng nhớ:

1. **Kết quả phụ thuộc vào các đối số đầu vào**, không phụ thuộc vào trạng thái ẩn như đồng hồ hệ thống, biến toàn cục đang thay đổi, database hiện tại hoặc thứ tự chạy thread.
2. **Không có tác dụng phụ quan sát được**: không ghi file, in console, sửa một đối tượng bên ngoài, gửi request, tăng bộ đếm toàn cục hoặc thay đổi dữ liệu đầu vào.

Nếu gọi cùng một hàm với **cùng dữ liệu đầu vào về mặt giá trị**, kết quả phải có cùng ý nghĩa; đây là tính xác định (*determinism*) trong ngữ cảnh phép tính đó.

Ví dụ đơn giản:

```java
static long subtotalCents(int quantity, long unitPriceCents) {
    if (quantity <= 0 || unitPriceCents < 0) {
        throw new IllegalArgumentException("Dữ liệu không hợp lệ");
    }
    return Math.multiplyExact((long) quantity, unitPriceCents);
}
```

Đây là phương thức đặt trong một class Java. Nó không đọc hoặc sửa trạng thái bên ngoài; `Math.multiplyExact` báo lỗi tràn số thay vì trả tổng tiền sai. Với cùng `quantity` và `unitPriceCents`, nó luôn trả cùng kết quả hoặc cùng loại lỗi tương ứng.

Ngược lại:

```java
static long calculatePrice(int quantity) {
    long price = GlobalPriceTable.currentPrice(); // Đọc trạng thái ẩn.
    System.out.println("Đang tính tiền");         // Ghi console.
    return quantity * price;
}
```

Đây là **mã minh họa một thiết kế có tác dụng phụ**, không phải chương trình độc lập; `GlobalPriceTable` là ví dụ giả định và không phải API Java chuẩn. Cùng `quantity` có thể cho kết quả khác nếu bảng giá đã đổi. Không nên viết test thuần cho phương thức này mà bỏ qua sự phụ thuộc môi trường.

Một hàm thuần vẫn có thể sử dụng **biến cục bộ mutable** bên trong, chẳng hạn cộng dồn tổng trong vòng `for`, miễn là không để lộ trạng thái mutable đó hoặc tác động lên những đối tượng do bên ngoài sở hữu. “Thuần” không có nghĩa **mọi câu lệnh đều phải dùng Stream**.

## 2. Phân biệt dữ liệu, quyết định và hành động

Có thể chia một luồng nghiệp vụ thành ba loại công việc:

| Loại công việc | Ví dụ | Nơi phù hợp |
| --- | --- | --- |
| **Đọc dữ liệu** | Đọc tệp, query database, nhận HTTP request, đọc clock | Boundary/adapter |
| **Quyết định** | Parse, validate, lọc, tính giá, áp dụng chính sách chiết khấu, render báo cáo thành `String` | Functional core |
| **Thực thi tác động** | Ghi tệp, lưu giao dịch, gửi email, gọi service, in log | Boundary/adapter |

Quy trình cơ bản:

```text
Thế giới ngoài
    |
    v
[Adapter đọc]  -- dữ liệu đã nhận -->  [Parse + Validate]
                                         |
                                         v
                                   [Tính toán thuần]
                                         |
                                         v
                                   [Tạo kết quả/plan]
                                         |
                                         v
[Adapter ghi]  <-- lệnh/đầu ra ----- [Lớp điều phối]
    |
    v
Thế giới ngoài
```

Trong sơ đồ, **parse** được xem là phép tính thuần khi nó chỉ nhận một chuỗi đã có sẵn rồi chuyển thành dữ liệu có cấu trúc, không tự mở file hay gọi API. **Render** cũng có thể thuần nếu chỉ tạo `String` từ giá trị đầu vào, chứ không tự `println`.

Ranh giới không nhất thiết là một file/class duy nhất. Mục tiêu là khiến side effect **dễ tìm thấy, dễ kiểm soát và dễ thay thế khi kiểm thử**.

## 3. Thiết kế ví dụ: tạo báo cáo giá trị đơn hàng

Bài toán: tệp đầu vào gồm những dòng dạng `SKU,quantity,unitPriceCents`. Ứng dụng cần tính tổng trước giảm giá, giảm 10% nếu tổng từ **10.000 cent** trở lên và xuất báo cáo.

Để ví dụ xác định và tránh trôi nổi số thực:

- Đơn giá dùng `long` là **số cent**.
- Số lượng dùng `int` và phải dương.
- Đơn giá không được âm; SKU không được rỗng.
- Thành tiền mỗi dòng là `quantity × unitPriceCents`.
- Giảm giá bằng `subtotal / 10` nếu đạt ngưỡng; phép chia số nguyên làm tròn xuống đến cent, được định nghĩa là **chính sách của ví dụ**, không phải quy tắc chung cho mọi nghiệp vụ tiền tệ.
- `Math.multiplyExact`, `Math.addExact` và `Math.subtractExact` giúp phát hiện overflow.
- Định dạng đầu vào cố ý đơn giản; chưa xử lý CSV đầy đủ có dấu phẩy trong trường quoted.

Thay vì thiết kế hàm `calculateFromFile(path)` vừa đọc file vừa tính toán vừa ghi file, ta tách:

```text
Files.readString(path)          -- impure I/O boundary
parse(rawText)                  -- pure
calculate(items)                -- pure
render(summary)                 -- pure
Files.writeString(path, report) -- impure I/O boundary
```

Lõi tính toán không biết đường dẫn tệp, console, database, HTTP hay cách chương trình được chạy.

## 4. Ví dụ Java 17+ đầy đủ, có thể biên dịch

Lưu vào tệp **`FunctionalCoreDemo.java`**:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;

public class FunctionalCoreDemo {
    record Item(String sku, int quantity, long unitPriceCents) {}

    record Summary(
            long subtotalCents,
            long discountCents,
            long payableCents
    ) {}

    // PURE: Chỉ đổi một dòng văn bản thành dữ liệu.
    static Item parseLine(String line) {
        String[] parts = line.split(",", -1);
        if (parts.length != 3) {
            throw new IllegalArgumentException("Sai định dạng: " + line);
        }
        return new Item(
                parts[0].trim(),
                Integer.parseInt(parts[1].trim()),
                Long.parseLong(parts[2].trim())
        );
    }

    // PURE: Không mở file, không sửa chuỗi đầu vào.
    static List<Item> parse(String rawText) {
        Objects.requireNonNull(rawText, "rawText");
        return rawText.lines()
                .filter(line -> !line.isBlank())
                .map(FunctionalCoreDemo::parseLine)
                .toList();
    }

    // PURE: Validation và tính toán chỉ phụ thuộc items.
    static Summary calculate(List<Item> items) {
        Objects.requireNonNull(items, "items");

        long subtotal = 0L;
        for (Item item : items) {
            Objects.requireNonNull(item, "item");
            if (item.sku() == null || item.sku().isBlank()
                    || item.quantity() <= 0
                    || item.unitPriceCents() < 0L) {
                throw new IllegalArgumentException("Item không hợp lệ");
            }

            long amount = Math.multiplyExact(
                    (long) item.quantity(),
                    item.unitPriceCents()
            );
            subtotal = Math.addExact(subtotal, amount);
        }

        long discount = subtotal >= 10_000L
                ? subtotal / 10L : 0L;
        long payable = Math.subtractExact(subtotal, discount);
        return new Summary(subtotal, discount, payable);
    }

    // PURE: Trả String; không println hay ghi file.
    static String render(Summary summary) {
        Objects.requireNonNull(summary, "summary");
        return "subtotalCents=" + summary.subtotalCents() + "\n"
                + "discountCents=" + summary.discountCents() + "\n"
                + "payableCents=" + summary.payableCents() + "\n";
    }

    // IMPURE BOUNDARY: Đọc và ghi file ở lớp điều phối.
    static String runFiles(Path source, Path destination)
            throws IOException {
        String rawText = Files.readString(
                source, StandardCharsets.UTF_8
        );

        List<Item> items = parse(rawText);
        Summary summary = calculate(items);
        String report = render(summary);

        Files.writeString(
                destination, report, StandardCharsets.UTF_8
        );
        return report;
    }

    public static void main(String[] args) throws IOException {
        if (args.length == 0) {
            // Demo không cần file để có stdout cố định.
            String sample = "PEN,2,2500\nBOOK,1,6000\n";
            System.out.print(render(calculate(parse(sample))));
        } else if (args.length == 2) {
            // Đọc/ghi file và in ra console đều là boundary.
            System.out.print(
                    runFiles(Path.of(args[0]), Path.of(args[1]))
            );
        } else {
            throw new IllegalArgumentException(
                    "Dùng: java FunctionalCoreDemo [input.txt output.txt]"
            );
        }
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 FunctionalCoreDemo.java
java FunctionalCoreDemo
```

**Stdout chính xác của chế độ không có tham số:**

```text
subtotalCents=11000
discountCents=1100
payableCents=9900
```

Tính tay: `PEN` có `2 × 2500 = 5000` cent; `BOOK` có `1 × 6000 = 6000` cent. Tổng `11000` cent đạt ngưỡng giảm 10%, nên chiết khấu `1100` và còn phải trả `9900`.

Chạy có hai tham số:

```bash
java FunctionalCoreDemo orders.txt report.txt
```

Chương trình đọc nội dung UTF-8 từ `orders.txt`, chuyển thành các `Item`, tính `Summary`, tạo văn bản và ghi `report.txt`. Tệp nguồn phải tồn tại và theo đúng định dạng; đường dẫn, quyền truy cập và lỗi I/O phụ thuộc môi trường. `Files.writeString` với các tùy chọn mặc định có thể tạo hoặc ghi đè nội dung tệp đích; chỉ sử dụng khi đúng chính sách ứng dụng.

Lưu ý: ví dụ phân tích một **định dạng ba trường phân cách bằng dấu phẩy**, chưa phải parser CSV theo chuẩn có escaping hoặc quoted fields. Trong ứng dụng thực, nếu SKU chứa dấu phẩy hoặc dữ liệu nhiều ngôn ngữ cần quoting, hãy dùng parser CSV đã được kiểm chứng hoặc định dạng đầu vào phù hợp. Sự lựa chọn parser không làm thay đổi cách tách lõi thuần khỏi boundary.

## 5. Vì sao phương thức `calculate()` là một lõi tính toán tốt?

Trong chương trình trên, `calculate()`:

- Chỉ nhận dữ liệu qua đối số `List<Item>`.
- Không gọi `Files`, `System.out`, `System.currentTimeMillis`, logger hay network.
- Không sửa danh sách đầu vào hoặc những `Item` record.
- Dùng biến `subtotal` cục bộ để tính, nhưng không để lộ biến mutable đó ra ngoài.
- Trả một `Summary` record mang giá trị tính toán, dễ so sánh bằng `equals()`.
- Ném ngoại lệ theo **quy tắc xác định** cho dữ liệu không hợp lệ hoặc overflow.

Vì vậy, phần quyết định tiền phải trả có thể được kiểm thử bằng dữ liệu thuần mà không cần tạo tệp, khởi động server hoặc thiết lập database.

Ví dụ kiểm thử nhỏ bên trong một class cùng package hoặc đặt trong chính class demo:

```java
Summary actual = calculate(List.of(
        new Item("PEN", 2, 2500L),
        new Item("BOOK", 1, 6000L)
));

Summary expected = new Summary(11000L, 1100L, 9900L);

if (!actual.equals(expected)) {
    throw new AssertionError("Sai kết quả: " + actual);
}
```

Đây là **snippet** cần ở trong phạm vi thấy được `Item`, `Summary`, `calculate()` và `java.util.List`; không phải chương trình độc lập. `record` cung cấp so sánh theo giá trị của các component, nên `Summary.equals()` phù hợp để đối chiếu.

**Phân biệt hàm thuần với hàm “không có ngoại lệ”:** một phép tính có thể ném `IllegalArgumentException` hoặc `ArithmeticException` theo dữ liệu. Nếu lỗi được xác định hoàn toàn bởi đầu vào, nó vẫn không tự động trở thành tác dụng phụ kiểu I/O. Trong hệ thống lớn, có thể biểu diễn lỗi mong đợi bằng kiểu kết quả như `Result<Success, Failure>` tự định nghĩa, thay vì dùng exception cho mọi trường hợp.

## 6. `parse()` và `render()` cũng có thể thuần

Nhiều lập trình viên chỉ tách phép tính tiền, nhưng vẫn để parser tự mở file hoặc renderer tự in console. Hãy quan sát khác biệt:

**Không nên gắn parser vào môi trường:**

```java
static List<Item> parseFile(Path path) throws IOException {
    return parse(Files.readString(path));
}
```

Đoạn minh họa có phụ thuộc môi trường: cùng `path` có thể có nội dung khác, file không tồn tại hoặc bị khóa. Nó là **adapter đọc**, không phải parser thuần.

**Parser thuần:**

```java
static List<Item> parse(String rawText) {
    return rawText.lines()
            .filter(line -> !line.isBlank())
            .map(FunctionalCoreDemo::parseLine)
            .toList();
}
```

Đoạn rút gọn trên minh họa ý tưởng; bản chạy đầy đủ ở mục 4 còn kiểm tra `null`. Parser chỉ phụ thuộc chuỗi đã truyền vào.

Tương tự, phương thức `render(summary)` **trả về** `String`. Phương thức `System.out.print(render(summary))` thực hiện side effect **ở ngoài** renderer. Nhờ vậy, cùng logic render có thể tái dùng để trả HTTP response, ghi file hay làm dữ liệu trong test.

Một thực hành tốt là làm các hàm thuần nhận **giá trị đã đủ thông tin**: parser nhận `String`, calculator nhận `List<Item>`, renderer nhận `Summary`. Đừng yêu cầu chúng tự tìm kiếm phụ thuộc toàn cục để hoàn thành công việc.

## 7. Thay state ẩn bằng đối số tường minh

Một số side effect khó nhận ra hơn `Files.writeString`:

| Nguồn phụ thuộc ẩn | Ví dụ khó kiểm thử | Đưa ra ranh giới |
| --- | --- | --- |
| Thời gian | `LocalDate.now()` trong logic giảm giá | Truyền `LocalDate today` hoặc `Clock` |
| Số ngẫu nhiên | `new Random().nextInt()` trong tính giá | Sinh quyết định ngoài, truyền kết quả/seed hoặc abstraction |
| Cấu hình runtime | `System.getenv("DISCOUNT")` | Đọc config một lần ở entrypoint, truyền `Policy` |
| Database | `repository.findPrice(sku)` bên trong `map` | Fetch dữ liệu trước, đưa bảng giá đã có vào core |
| Network | `httpClient.send(...)` khi validate | Adapter gọi HTTP, core validate dữ liệu phản hồi |
| Locale/time zone mặc định | Format không khai báo locale | Truyền `Locale`/`ZoneId` hoặc cấu hình đã chọn |

Ví dụ một chính sách có phụ thuộc ngày:

```java
static boolean isPromotionActive(
        LocalDate today,
        LocalDate from,
        LocalDate through
) {
    return !today.isBefore(from) && !today.isAfter(through);
}
```

Đây là snippet bên trong class, cần `import java.time.LocalDate;`. Hàm không gọi `LocalDate.now()`, nên test có thể truyền ngày bất kỳ. Entry point hoặc adapter có thể đọc `LocalDate.now(clock)` rồi truyền vào, còn chính sách ngày vẫn là phép tính thuần.

`Clock` là kỹ thuật hữu ích khi một dịch vụ có nhiều nơi cần lấy thời gian; **truyền hẳn một giá trị thời gian** vào hàm tính toán thường còn đơn giản hơn nếu chức năng chỉ cần một thời điểm cố định.

## 8. Stream thuần không phải cứ dùng `map()` là đủ

Các thao tác Stream thường phù hợp để biểu diễn biến đổi dữ liệu:

```java
List<String> normalized = names.stream()
        .filter(name -> !name.isBlank())
        .map(name -> name.trim().toUpperCase(Locale.ROOT))
        .toList();
```

Đây là snippet trong phương thức, cần `java.util.List`, `java.util.Locale`; `names` là `List<String>` không chứa `null`. Nó tạo list kết quả mà không sửa `names`.

Nhưng nếu callback làm I/O, bản thân `Stream` không làm side effect biến mất:

```java
// KHÔNG phải functional core thuần:
orders.stream()
        .map(order -> {
            auditLogger.log(order);     // Side effect.
            return pricingService.call(order); // Có thể là I/O.
        })
        .toList();
```

Các tên `auditLogger`, `pricingService`, `orders` trong snippet là phụ thuộc của ứng dụng, không phải API Java có sẵn. Code này có thể chịu ảnh hưởng từ thứ tự chạy, lỗi mạng, timeout và retry.

Tốt hơn, nếu có thể:

1. Đọc dữ liệu bên ngoài ở adapter.
2. Chuyển dữ liệu thành kiểu giá trị dễ tính toán.
3. Dùng `map`/`filter`/`reduce` hoặc vòng `for` thuần để đưa ra quyết định.
4. Thu lại kết quả bằng `toList()`, `collect()` hoặc đối tượng trả về.
5. Thực hiện các hành động đọc/ghi tiếp theo tại ranh giới có chủ đích.

**`peek()` không phải nơi thích hợp để ghi I/O bắt buộc.** Một số pipeline có thể tối ưu hóa và không gọi callback trung gian nếu terminal operation không cần chúng, chẳng hạn `count()` trên nguồn có kích thước đã biết. Với parallel stream, lịch gọi `peek` cũng không nhất thiết theo encounter order. Logic nghiệp vụ không nên phụ thuộc vào số lần gọi hoặc thứ tự side effect trong intermediate operation.

## 9. Trạng thái mutable ở đâu thì được?

Thiết kế theo hàm **không cấm** mọi biến mutable. Cần phân biệt:

**Biến cục bộ nằm hoàn toàn trong lời gọi hàm**

```java
static long sumCents(List<Long> amounts) {
    long total = 0;
    for (long amount : amounts) {
        total = Math.addExact(total, amount);
    }
    return total;
}
```

Đây là snippet trong class có `java.util.List`. Nếu không sửa `amounts`, chỉ sử dụng `total` cục bộ rồi trả về một `long`, hàm có thể thuần. Vòng `for` không khiến nó “kém functional” về ngữ nghĩa.

**Trạng thái dùng chung/được truyền từ ngoài**

```java
static long sumWithSideEffect(
        List<Long> amounts, long[] sharedTotal
) {
    for (long amount : amounts) {
        sharedTotal[0] += amount;
    }
    return sharedTotal[0];
}
```

Đây là ví dụ có side effect: caller giữ `sharedTotal` và quan sát nó bị sửa. Khi chạy đồng thời còn có thể xảy ra race condition.

Nếu cần nhiều kết quả, trả một `record` chứa các giá trị thay vì sửa nhiều tham số đầu ra. Khi cần xây dựng một collection tạm trong hàm, có thể tạo mới rồi trả **bản sao bất biến** bằng `List.copyOf(...)` nếu các phần tử cũng an toàn để chia sẻ. Nhớ rằng `List.copyOf` chỉ sao chép cấu trúc list; nó **không deep-copy** đối tượng mutable ở bên trong.

## 10. Kiểm thử nhanh phần thuần không cần I/O

Có thể kiểm tra từng hàm độc lập:

| Tình huống | Đầu vào | Kết quả cần có |
| --- | --- | --- |
| Tổng dưới ngưỡng | `Item("A",1,2500)` | `subtotal=2500,discount=0,payable=2500` |
| Tổng đúng ngưỡng | `Item("A",4,2500)` | `subtotal=10000,discount=1000,payable=9000` |
| Tổng trên ngưỡng | `Item("A",2,6000)` | `subtotal=12000,discount=1200,payable=10800` |
| Danh sách rỗng | `List.of()` | `Summary(0,0,0)` |
| Số lượng không dương | `Item("A",0,2500)` | `IllegalArgumentException` |
| Đơn giá âm | `Item("A",1,-1)` | `IllegalArgumentException` |
| Chuỗi dòng sai định dạng | `"A,2"` | `IllegalArgumentException` |
| Tổng vượt `long` | Dữ liệu đủ lớn gây overflow | `ArithmeticException` |

Khi test cần kiểm tra ngoại lệ trong JUnit 5, có thể dùng `assertThrows`; tuy nhiên ví dụ Java ở mục 4 không cần thư viện kiểm thử ngoài JDK.

Một kiểm tra nhanh bằng Java bên trong class:

```java
Summary a = calculate(List.of(new Item("A", 4, 2500L)));
if (!a.equals(new Summary(10000L, 1000L, 9000L))) {
    throw new AssertionError(a);
}
```

Đây là snippet, không phải file chạy độc lập. Nó không cần tạo input/output file; chạy nhanh và kết quả ổn định.

**Test boundary thì khác:** cần kiểm thử tệp không tồn tại, quyền truy cập, ký tự UTF-8, file đích đã có, và lỗi ghi giữa chừng. Những điều ấy được kiểm thử tại lớp I/O, không trộn vào bài kiểm tra công thức giảm giá.

## 11. Thiết kế kết quả cho tác dụng phụ: command, plan hoặc event

Trong một số nghiệp vụ, lõi tính toán không chỉ trả tổng tiền mà còn quyết định **hành động nào cần thực hiện**. Thay vì tự gửi email hoặc ghi database, nó có thể trả một mô tả dữ liệu:

```java
record NotificationPlan(String recipientId, String message) {}

static NotificationPlan planReceipt(
        String customerId,
        long payableCents
) {
    return new NotificationPlan(
            customerId,
            "Đã thanh toán: " + payableCents + " cent"
    );
}
```

Đây là khai báo record và phương thức minh họa bên trong class. `planReceipt` chỉ tạo một giá trị; nó **không gửi** thông báo.

Lớp vỏ có thể nhận `NotificationPlan`, xác minh chính sách gửi rồi dùng adapter bên ngoài để giao tiếp với dịch vụ gửi thông báo. Cách này đem lại lợi ích:

- Test “có nên gửi thông báo và gửi nội dung gì” không cần kết nối mail server.
- Có thể log và phê duyệt kế hoạch trước khi thực thi.
- Có thể áp dụng transaction, outbox hoặc cơ chế idempotency ở lớp adapter.
- Đổi dịch vụ gửi thông báo không buộc sửa logic tạo nội dung.

Dù vậy, **một plan thuần không tự đảm bảo hành động xảy ra đúng một lần**. Exactly-once, retry, transaction và commit là vấn đề của ranh giới I/O và hạ tầng, phải thiết kế riêng.

## 12. Ranh giới I/O không có nghĩa “bắt hết lỗi và bỏ qua”

Trong `runFiles`, `Files.readString` hoặc `Files.writeString` có thể ném `IOException`. `parseLine` có thể ném `NumberFormatException` hoặc `IllegalArgumentException`, còn `calculate` có thể ném `ArithmeticException` do overflow.

Một lớp điều phối có thể phân nhóm lỗi:

| Nhóm lỗi | Ví dụ | Chính sách thường cần |
| --- | --- | --- |
| Dữ liệu sai | Thiếu cột, số lượng âm, giá không hợp lệ | Trả lỗi validation, không tạo kết quả nghiệp vụ giả |
| Tràn số | Tổng vượt `long` | Báo lỗi rõ ràng hoặc đổi kiểu tiền/phép tính |
| Lỗi đọc | Không tìm thấy tệp, quyền truy cập bị từ chối | Chọn retry có điều kiện hoặc trả lỗi |
| Lỗi ghi | Đĩa đầy, lỗi mạng, file bị khóa | Cảnh báo trạng thái ghi một phần, không giả định transaction |
| Lỗi dịch vụ ngoài | Timeout, 5xx, dữ liệu phản hồi không hợp lệ | Retry có giới hạn/idempotency và điều phối phù hợp |

Không nên thay `catch (Exception ignored) { return new Summary(0,0,0); }`: khi đó lỗi đọc file hoặc dữ liệu sai có thể bị biến thành một đơn hàng hợp lệ tổng bằng 0.

Nếu cần ghi file an toàn, có thể ghi vào tệp tạm rồi **đổi tên nguyên tử khi file system hỗ trợ**. Trong database, cần transaction. Trong môi trường mạng, cần idempotency key/outbox hoặc chính sách retry. Những cơ chế ấy nằm trong shell/adapter và không làm thay đổi công thức tính tiền ở core.

## 13. Những lỗi thiết kế thường gặp

| Sai lầm | Tác hại | Hướng sửa |
| --- | --- | --- |
| Hàm tính giá tự đọc bảng giá từ DB | Test đòi DB và kết quả phụ thuộc trạng thái ẩn | Truyền dữ liệu bảng giá đã truy vấn vào core |
| Đọc `LocalDate.now()` trong điều kiện ưu đãi | Kết quả thay đổi theo thời gian thật | Truyền thời điểm/clock do caller chọn |
| `map()` hoặc `peek()` trực tiếp ghi file | Side effect nằm trong pipeline lazy, khó dự đoán lúc thực thi | Thu kết quả rồi ghi ở boundary |
| Sửa collection đầu vào trong `filter` | Vi phạm nguyên tắc non-interfering, có thể lỗi khi duyệt | Tạo collection kết quả mới |
| Dùng `parallelStream().forEach(sharedList::add)` | Race và thứ tự không bảo đảm | Dùng `toList()`/`collect()` |
| Trả thẳng một `List` mutable nội bộ rồi tiếp tục sửa | Caller quan sát kết quả bị đổi sau khi trả về | Trả bản sao bất biến khi phù hợp |
| Nhầm vòng `for` cục bộ với side effect bên ngoài | Bỏ lỡ cách viết đơn giản, dễ đọc | Phân biệt mutation cục bộ với trạng thái chia sẻ |
| Dùng `double` để tính tiền mà không nêu chính sách làm tròn | Có thể gây sai số thập phân | Dùng đơn vị cent hoặc `BigDecimal` với scale/rounding rõ |
| Gộp tất cả các exception thành giá trị mặc định | Che dữ liệu sai và lỗi môi trường | Phân biệt lỗi dữ liệu, lỗi tính toán, lỗi I/O |
| Xem `Files.writeString` là transaction | File có thể bị ghi một phần khi lỗi | Chọn temp file/atomic move hoặc transaction khi cần |
| Mọi phương thức đều nhận repository/logger/client | Core bị gắn chặt vào infrastructure | Đưa phép đọc/ghi ra adapter, core nhận giá trị |
| “Thuần” nhưng dùng đối tượng mutable đang thay đổi ở thread khác | Cùng tham chiếu đầu vào có thể có nội dung khác | Chụp snapshot/giá trị bất biến trước tính toán |

## 14. Quy trình áp dụng trong dự án thực tế

Khi chuyển một đoạn code nghiệp vụ có nhiều tác dụng phụ sang thiết kế theo hàm, có thể làm theo các bước:

1. **Liệt kê mọi nguồn I/O/trạng thái ẩn:** DB, HTTP, file, thời gian, random, environment, logger, shared mutable fields.
2. **Xác định đầu vào thật sự của phép quyết định:** dữ liệu cần thiết, chính sách, ngày áp dụng, tham số cấu hình.
3. **Thiết kế value objects:** `record`, collection mới, enum hoặc DTO mang các giá trị đủ thông tin.
4. **Tách các hàm thuần:** parse, normalize, validate, calculate, select, plan, render.
5. **Để shell điều phối:** đọc nguồn, chuyển dữ liệu vào core, nhận kết quả, thực thi hành động bên ngoài.
6. **Kiểm thử core bằng giá trị:** đầu vào bình thường, biên, lỗi dữ liệu, overflow, trạng thái rỗng.
7. **Kiểm thử adapter riêng:** quyền file, HTTP timeout, transaction, retry, mã hóa, định dạng payload.
8. **Đo tác động thay đổi:** dễ test hơn, số dependency giảm, đặc tính đồng thời an toàn hơn; nhưng không đánh đổi hiệu năng hoặc làm kiến trúc phức tạp quá mức cho bài toán nhỏ.

Thiết kế tốt thường là **một vài ranh giới rõ ràng**, không phải hàng chục lớp abstraction vô nghĩa. Khi một hành động thật sự phải diễn ra ở giữa chuỗi quyết định, hãy chia quy trình thành các bước: **tính request thuần → thực thi I/O → tính quyết định tiếp theo từ response**. Cách này giữ những chỗ có tác dụng phụ hiển thị rõ mà vẫn linh hoạt.

## Tự kiểm tra kiến thức

**Câu 1.** `String report = render(summary)` có là side effect không, nếu `render` chỉ nối chuỗi?

**Đáp án:** Không. Nó chỉ tạo giá trị `String` từ `summary`. `System.out.print(report)` hoặc `Files.writeString(..., report)` mới là tác dụng phụ.

**Câu 2.** Dùng biến `long subtotal` và vòng `for` bên trong `calculate` có khiến hàm không thuần?

**Đáp án:** Không, miễn biến đó chỉ tồn tại trong lời gọi hàm, không sửa dữ liệu đầu vào hay trạng thái bên ngoài, và kết quả phụ thuộc hoàn toàn vào đầu vào.

**Câu 3.** Muốn tính ưu đãi theo ngày hiện tại, nên gọi `LocalDate.now()` trong core hay truyền một ngày do shell cung cấp?

**Đáp án:** Nên truyền ngày/clock đã chọn để test thuần không phụ thuộc đồng hồ hệ thống.

**Câu 4.** `parallelStream().map(x -> { shared.add(x); return x; }).toList()` có an toàn vì terminal là `toList()` không?

**Đáp án:** Không. `shared.add` trong mapper là side effect chia sẻ, có thể gây race; `toList()` không bảo vệ biến ngoài.

**Câu 5.** Nếu file đã ghi một nửa rồi lỗi, việc tính toán thuần có giúp rollback tự động không?

**Đáp án:** Không. Tính thuần chỉ giúp tách quyết định khỏi tác động. Rollback, atomic replace hoặc transaction phải được thiết kế ở boundary.

**Câu 6.** Khi phải gửi email sau tính tiền, lõi có thể trả loại kết quả nào?

**Đáp án:** Một `NotificationPlan` hoặc giá trị mô tả thông điệp cần gửi. Adapter sẽ gửi email và xử lý retry/idempotency.

## Ghi nhớ

- **Functional core:** nhận các giá trị rõ ràng, thực hiện phép quyết định, trả giá trị mới; tránh I/O và trạng thái ẩn.
- **Imperative shell:** đọc/ghi thế giới ngoài, đưa dữ liệu vào core và áp dụng kết quả ra môi trường.
- `parse(String)`, `calculate(List<Item>)`, `render(Summary)` có thể thuần; `Files.readString`, `Files.writeString`, network, đồng hồ và console là side effect ở boundary.
- Không cần bỏ vòng `for` hoặc biến cục bộ để đạt tính thuần; quan trọng là **không tạo tác dụng phụ quan sát được**.
- **Đưa thời gian, cấu hình, random và bảng giá thành dữ liệu đầu vào tường minh** khi chúng ảnh hưởng quyết định.
- Kiểm thử lõi bằng các giá trị bất biến, kiểm thử I/O riêng; xây dựng lỗi/retry/transaction ở đúng ranh giới.
