# Tách pipeline dài thành các bước có tên và hợp đồng rõ ràng

## 1. Mục tiêu và bối cảnh

Trong module **`JAVA_STREAM_API`**, việc xử lý dữ liệu khai báo bằng Java Stream API thường bắt đầu với một nguồn, đi qua các thao tác trung gian lazy như `filter`, `map` và `flatMap`, rồi kết thúc bằng `reduce`, `collect` hoặc một terminal operation khác. Khi thêm quy tắc nghiệp vụ, grouping, sorting và xử lý lỗi, một pipeline ngắn ban đầu có thể trở thành **một chuỗi lambda rất dài**.

Vấn đề của pipeline dài không phải chỉ là số dòng. Nó làm khó việc trả lời các câu hỏi quan trọng:

- Đầu vào được kỳ vọng ở định dạng nào? `null`, chuỗi rỗng và số âm xử lý ra sao?
- Một bước đang **chuẩn hóa**, **kiểm tra hợp lệ**, **lọc** hay **tổng hợp**?
- Khi dữ liệu sai, hệ thống ném lỗi, bỏ bản ghi hay thu vào danh sách lỗi?
- Khi kết quả bất thường, bước nào làm mất hoặc nhân đôi phần tử?
- Thứ tự kết quả có ý nghĩa không? `groupingBy` và `parallel` có thay đổi giả định đó không?
- Có thể kiểm thử từng quy tắc mà không cần chạy cả ứng dụng không?

Bài học thuộc chương **Gỡ lỗi và kiểm thử pipeline**, hướng dẫn cách **tách pipeline dài thành các bước có tên và hợp đồng rõ ràng**. Ta sẽ thực hành trên ví dụ đơn hàng, chuyển từ một biểu thức khó bảo trì sang các hàm Java 8+ dễ đọc, kiểm thử, đo lường và thay đổi.

Sau bài học, bạn có thể:

1. Xác định **ranh giới nghiệp vụ** để tách các thao tác trong pipeline.
2. Ghi hợp đồng của từng bước: kiểu vào/ra, tiền điều kiện, hậu điều kiện, thứ tự, side effect và chính sách lỗi.
3. Viết các hàm `normalize`, `paidOnly`, `summarize` bằng kiểu dữ liệu và tên có ý nghĩa.
4. Phân biệt **hàm trên một phần tử**, **hàm nhận/trả `Stream`** và **terminal operation trả kết quả hữu hình**.
5. Kiểm thử riêng từng quy tắc và đối chiếu kết quả đầu-cuối với thuật toán tham chiếu.
6. Dùng log, `peek` và materialize tạm thời để chẩn đoán mà không phụ thuộc side effect.
7. Giữ đúng tính lazy, một-lần-tiêu-thụ, quản lý I/O và các điều kiện song song hóa.

## 2. Nhận diện một pipeline khó gỡ lỗi

Giả sử nghiệp vụ nhận các giao dịch gồm mã đơn hàng, khách hàng, trạng thái và số tiền tính bằng **cent**. Yêu cầu:

- Chuẩn hóa khoảng trắng của mã đơn và mã khách hàng.
- Chuẩn hóa trạng thái thành chữ hoa theo `Locale.ROOT`.
- **Từ chối** bản ghi không hợp lệ: `null`, mã rỗng, trạng thái không hỗ trợ hoặc số tiền âm.
- Chỉ giữ những đơn **PAID**.
- Tính tổng số tiền và số đơn theo khách hàng.
- Sắp xếp kết quả theo tổng tiền **giảm dần**, nếu bằng nhau theo mã khách hàng **tăng dần**.

Một pipeline có thể bị viết dồn:

```java
List<CustomerSummary> result = source.stream()
    .map(row -> /* nhiều nhánh normalize và validate */)
    .filter(sale -> "PAID".equals(sale.status))
    .collect(Collectors.groupingBy(
        sale -> sale.customerId,
        Collectors.summarizingLong(sale -> sale.amountCents)
    ))
    .entrySet().stream()
    .map(entry -> /* dựng CustomerSummary */)
    .sorted(/* comparator có nhiều điều kiện */)
    .collect(Collectors.toList());
```

Đoạn minh họa cố ý để trống những chi tiết được chuyển thành **hàm có tên** ở phần sau. Khi đọc dòng `map` đầu tiên, ta chưa biết quy tắc nào đang được thực hiện; nếu sau này thêm xử lý `null` hoặc refund, phần còn lại dễ bị ảnh hưởng ngoài ý muốn.

**Dấu hiệu cần refactor:**

- Lambda nhiều dòng vừa biến đổi dữ liệu vừa kiểm tra lỗi và ghi log.
- Biểu thức có nhiều phép `collect` lồng nhau khiến kiểu dữ liệu khó nhận biết.
- Mỗi nơi sử dụng pipeline lại sao chép cùng một đoạn `filter`/`map`.
- Không xác định được bước nào làm thay đổi số phần tử.
- Quy tắc xử lý lỗi bị ẩn trong `filter(x -> x != null)` hoặc `catch` trả giá trị mặc định.
- Test chỉ so sánh kết quả cuối với một vài mẫu "đẹp", không có ca lỗi hay dữ liệu rỗng.

**Mục tiêu refactor không phải tạo càng nhiều hàm càng tốt.** Mục tiêu là làm cho mỗi tên bước thể hiện một quy tắc có thể mô tả, kiểm chứng và thay đổi riêng.

## 3. Hợp đồng của một bước xử lý nên ghi gì?

Đối với mỗi bước, có thể ghi ngắn gọn:

| Thành phần | Câu hỏi |
| --- | --- |
| **Tên và trách nhiệm** | Bước giải quyết một quy tắc nào? Tên có phản ánh đúng quy tắc không? |
| **Kiểu dữ liệu vào/ra** | Nhận `RawSale` hay `Sale`? Trả `Stream<Sale>`, `List<Sale>` hay `Map`? |
| **Tiền điều kiện** | Dữ liệu phải khác `null`? Đã chuẩn hóa? Có thứ tự? |
| **Hậu điều kiện** | Kết quả luôn hợp lệ? Có thể rỗng? Có giữ thứ tự/giá trị trùng không? |
| **Chính sách lỗi** | Ném ngoại lệ, loại bỏ bản ghi hay thu lỗi riêng? |
| **Số lượng phần tử** | Một-một, loại bớt, phát nhiều hay tổng hợp? |
| **Tác dụng phụ** | Có sửa nguồn, gọi I/O, cập nhật biến dùng chung không? |
| **Lazy/eager** | Chỉ xây pipeline hay thực sự tiêu thụ và giữ kết quả trong RAM? |

Hợp đồng có thể trình bày bằng Javadoc, bảng ngắn hoặc test; không nhất thiết viết tài liệu quá dài cho một hàm nhỏ.

### 3.1. Hợp đồng của các bước trong ví dụ

| Bước | Đầu vào → Đầu ra | Quy tắc | Cardinality |
| --- | --- | --- | --- |
| `normalizeSale` | `RawSale → Sale` | Kiểm tra hợp lệ, trim mã, chuẩn hóa status; sai thì ném `IllegalArgumentException` | 1 → 1 hoặc lỗi |
| `normalize` | `Stream<RawSale> → Stream<Sale>` | Áp dụng `normalizeSale` lazily cho từng phần tử | Bảo toàn số lượng khi không lỗi |
| `paidOnly` | `Stream<Sale> → Stream<Sale>` | Chỉ giữ đơn `PAID` | 0 hoặc 1 đầu ra/đầu vào |
| `summarize` | `Stream<Sale> → List<CustomerSummary>` | Nhóm, cộng tiền, đếm đơn, sắp xếp | Nhiều đơn → một dòng/khách |
| `process` | `List<RawSale> → List<CustomerSummary>` | Kết nối các bước; trả list không cho sửa | Kết quả hữu hình |

**Thứ tự chạy logic:** `normalize` trước `paidOnly` nghĩa là **mọi bản ghi đều được kiểm tra**, kể cả bản ghi sau đó không được chọn để tổng hợp. Nếu doanh nghiệp muốn bỏ qua dòng `PENDING` bị lỗi mà không báo, đó là **một chính sách khác**, phải được định nghĩa riêng, không tự đổi vị trí bộ lọc để "sửa lỗi".

### 3.2. Hợp đồng phải ghi rõ thứ tự

Một nguồn `List` có encounter order; `map` và `filter` trên ordered stream giữ thứ tự logic của các phần tử còn lại. Nhưng `Collectors.groupingBy` mặc định **không cam kết thứ tự duyệt các khóa trong `Map`**.

Vì vậy, sau nhóm cần **sắp xếp tường minh** theo tổng tiền và mã khách hàng nếu báo cáo yêu cầu thứ tự xác định. Đừng dựa vào thứ tự hiển thị của một `HashMap` trong lần chạy hiện tại.

## 4. Tách hai cấp: hàm biến đổi một bản ghi và hàm xử lý stream

Một cách tách rõ ràng là:

```text
RawSale
   |
normalizeSale(RawSale)            // Quy tắc cấp bản ghi
   |
Sale
   |
normalize(Stream<RawSale>)       // Bước trung gian lazy
   |
Stream<Sale>
   |
paidOnly(Stream<Sale>)           // Lọc theo nghiệp vụ
   |
Stream<Sale>
   |
summarize(Stream<Sale>)          // Terminal: grouping + sort
   |
List<CustomerSummary>
```

Tên `normalizeSale` khác `normalize` có chủ đích:

- `normalizeSale` là **hàm thuần** ở cấp bản ghi, thích hợp cho unit test trực tiếp.
- `normalize` là **hàm xây pipeline**. Nó chưa kiểm tra mọi bản ghi ngay khi được gọi; việc kiểm tra diễn ra trong quá trình tiêu thụ.
- `summarize` là **điểm kết thúc**: gọi `collect` và tạo `List`. Nó không còn lazy.

Nếu chỉ đặt tên cho một biến `Stream<Sale> stage1` hoặc `Stream<Sale> stage2` thì chưa giải quyết vấn đề hợp đồng. Hãy đặt tên theo **quy tắc hoặc ý nghĩa dữ liệu**, không theo số thứ tự.

## 5. Chương trình Java 8+ hoàn chỉnh: pipeline có tên

Tạo file `NamedPipelineExample.java`. Chương trình không dùng `record`, `Stream.toList()` hay API chỉ có ở các JDK mới, nên phù hợp với Java 8.

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class NamedPipelineExample {

    static final class RawSale {
        final String orderId;
        final String customerId;
        final String status;
        final long amountCents;

        RawSale(String orderId, String customerId,
                String status, long amountCents) {
            this.orderId = orderId;
            this.customerId = customerId;
            this.status = status;
            this.amountCents = amountCents;
        }
    }

    static final class Sale {
        final String orderId;
        final String customerId;
        final String status;
        final long amountCents;

        Sale(String orderId, String customerId,
                String status, long amountCents) {
            this.orderId = orderId;
            this.customerId = customerId;
            this.status = status;
            this.amountCents = amountCents;
        }
    }

    static final class CustomerSummary {
        final String customerId;
        final long orderCount;
        final long totalCents;

        CustomerSummary(String customerId,
                long orderCount, long totalCents) {
            this.customerId = customerId;
            this.orderCount = orderCount;
            this.totalCents = totalCents;
        }

        @Override
        public String toString() {
            return customerId
                + " total=" + totalCents
                + " count=" + orderCount;
        }
    }

    // Hợp đồng: null/rỗng không hợp lệ; trả chuỗi đã trim.
    static String requiredText(String text, String field) {
        if (text == null || text.trim().isEmpty()) {
            throw new IllegalArgumentException(
                field + " khong duoc rong");
        }
        return text.trim();
    }

    // Hợp đồng: một RawSale hợp lệ -> một Sale chuẩn hóa;
    // dữ liệu sai -> IllegalArgumentException.
    static Sale normalizeSale(RawSale raw) {
        if (raw == null) {
            throw new IllegalArgumentException(
                "Ban ghi khong duoc null");
        }

        String orderId = requiredText(
            raw.orderId, "orderId");
        String customerId = requiredText(
            raw.customerId, "customerId");
        String status = requiredText(
            raw.status, "status")
            .toUpperCase(Locale.ROOT);

        if (!status.equals("PAID")
                && !status.equals("PENDING")
                && !status.equals("REFUNDED")) {
            throw new IllegalArgumentException(
                "status khong ho tro: " + status);
        }
        if (raw.amountCents < 0) {
            throw new IllegalArgumentException(
                "amountCents phai >= 0");
        }

        return new Sale(
            orderId, customerId, status, raw.amountCents);
    }

    // Chỉ xây một intermediate stage, chưa tiêu thụ nguồn.
    static Stream<Sale> normalize(
            Stream<RawSale> source) {
        Objects.requireNonNull(source, "source");
        return source.map(
            NamedPipelineExample::normalizeSale);
    }

    // Hợp đồng: đầu vào đã chuẩn hóa; chỉ giữ PAID.
    static Stream<Sale> paidOnly(Stream<Sale> sales) {
        Objects.requireNonNull(sales, "sales");
        return sales.filter(
            sale -> "PAID".equals(sale.status));
    }

    // Terminal stage: grouping, đếm/tổng tiền, sort.
    static List<CustomerSummary> summarize(
            Stream<Sale> paidSales) {
        Objects.requireNonNull(paidSales, "paidSales");

        Map<String, LongSummaryStatistics> byCustomer =
            paidSales.collect(
                Collectors.groupingBy(
                    sale -> sale.customerId,
                    Collectors.summarizingLong(
                        sale -> sale.amountCents)
                )
            );

        Comparator<CustomerSummary> order =
            Comparator.comparingLong(
                    (CustomerSummary s) -> s.totalCents)
                .reversed()
                .thenComparing(s -> s.customerId);

        return byCustomer.entrySet().stream()
            .map(entry -> new CustomerSummary(
                entry.getKey(),
                entry.getValue().getCount(),
                entry.getValue().getSum()))
            .sorted(order)
            .collect(Collectors.toList());
    }

    // Điểm vào nghiệp vụ: không sửa source;
    // trả list không cho sửa về mặt cấu trúc.
    static List<CustomerSummary> process(
            List<RawSale> source) {
        Objects.requireNonNull(source, "source");

        List<CustomerSummary> result = summarize(
            paidOnly(normalize(source.stream())));

        return Collections.unmodifiableList(result);
    }

    public static void main(String[] args) {
        List<RawSale> input = Arrays.asList(
            new RawSale(" O-1 ", " KH-A ",
                "paid", 1000),
            new RawSale("O-2", "KH-B",
                "PAID", 2500),
            new RawSale("O-3", "KH-A",
                "REFUNDED", 9999),
            new RawSale("O-4", "KH-A",
                "PAID", 3000),
            new RawSale("O-5", "KH-C",
                "PENDING", 9900),
            new RawSale("O-6", "KH-B",
                "paid", 500),
            new RawSale("O-7", "KH-A",
                "PAID", 2000)
        );

        process(input).forEach(System.out::println);
    }
}
```

Kết quả mong đợi:

```text
KH-A total=6000 count=3
KH-B total=3000 count=2
```

### 5.1. Vì sao cách tách này dễ kiểm thử?

- `normalizeSale` kiểm thử bằng **một bản ghi** mà không cần dựng toàn bộ luồng.
- `paidOnly` kiểm thử số phần tử còn lại từ một stream nhỏ đã chuẩn hóa.
- `summarize` kiểm thử riêng quy tắc grouping, số lượng, tổng và thứ tự.
- `process` có một test đầu-cuối xác nhận các bước tương tác đúng.
- Tên phương thức và kiểu trả về thể hiện rõ **điểm chuyển từ lazy sang eager**.

Trong ứng dụng thực, các lớp dữ liệu có thể được tách thành file riêng. Ở đây đặt trong một lớp để ví dụ **tự chứa** và dễ biên dịch.

### 5.2. Hợp đồng có giới hạn về miền số

`amountCents` dùng `long`, còn `Collectors.summarizingLong` tổng hợp theo `long`. Nếu tổng tiền có thể vượt `Long.MAX_VALUE`, kết quả có nguy cơ tràn số. Ví dụ giả định **tổng nằm trong miền long**; nghiệp vụ đòi tính tiền chính xác ngoài miền này nên dùng thuật toán kiểm tra tràn hoặc `BigInteger`.

Đơn hàng `REFUNDED` được **loại khỏi báo cáo**, không tự động tạo số âm để khấu trừ. Nếu nghiệp vụ cần doanh thu ròng, phải định nghĩa rõ cách xử lý refund và viết một bước riêng; không âm thầm đổi `paidOnly`.

### 5.3. Không lẫn dữ liệu được chuẩn hóa với dữ liệu thô

`RawSale` và `Sale` là hai kiểu khác nhau, dù có các trường gần giống nhau. Việc tách kiểu giúp tránh:

```java
// Ý tưởng không nên dùng:
// paidOnly(source.stream()); // Không phải Stream<Sale>.
```

Compiler sẽ không cho truyền `Stream<RawSale>` vào phương thức nhận `Stream<Sale>`. Hợp đồng kiểm tra hợp lệ không còn chỉ nằm trong bình luận mà được hỗ trợ một phần bằng **hệ thống kiểu**.

## 6. Hàm có tên không làm mất tính lazy của Stream

Phân biệt hai lớp thao tác:

```java
Stream<NamedPipelineExample.Sale> pipeline =
    NamedPipelineExample.paidOnly(
        NamedPipelineExample.normalize(input.stream())
    );

// Tại đây, normalizeSale chưa được bảo đảm đã chạy.
long count = pipeline.count(); // Terminal: tiêu thụ pipeline.
```

`normalize` và `paidOnly` trả `Stream` để xây pipeline. Chúng không tự tạo list trung gian. Vì vậy, bạn có thể tách code theo trách nhiệm **mà vẫn giữ khả năng xử lý lazy**.

Nhưng `summarize` gọi `collect`; đó là điểm **terminal**. Sau khi `summarize(stream)` trả kết quả, stream đầu vào đã bị tiêu thụ và không thể dùng lại.

### 6.1. Sai: dùng một stream cho hai phép kết thúc

```java
Stream<NamedPipelineExample.Sale> sales =
    NamedPipelineExample.normalize(input.stream());

long count = sales.count();

// KHÔNG ĐƯỢC: Stream đã tiêu thụ.
// List<NamedPipelineExample.Sale> data =
//     sales.collect(Collectors.toList());
```

Nếu cần đếm và liệt kê trên một tập **hữu hạn, nhỏ**, có thể thu một lần vào `List` rồi tạo các stream mới từ list. Nếu muốn giữ xử lý lazy, hãy tạo một stream mới từ **nguồn có thể mở lại** cho mỗi terminal operation. Không phải nguồn nào (đặc biệt nguồn I/O) cũng có thể đọc lại miễn phí.

### 6.2. Không đánh đồng xây pipeline với chạy validation

Đặt `normalizeSale` trong `map` khiến việc kiểm tra hợp lệ diễn ra **khi phần tử được tiêu thụ**:

```java
Stream<NamedPipelineExample.Sale> sales =
    NamedPipelineExample.normalize(input.stream());

// Lúc này dữ liệu sai chưa nhất thiết gây lỗi.
List<NamedPipelineExample.Sale> checked =
    sales.collect(Collectors.toList());
```

Ngoài ra, một terminal operation **short-circuiting** như `findFirst` có thể không duyệt mọi bản ghi; một số tối ưu hóa như `count` với nguồn có kích thước đã biết còn có thể bỏ những phép `map` không làm đổi số phần tử. Do đó, **không dùng `map` như một lời hứa rằng toàn bộ nguồn chắc chắn đã được kiểm tra**.

Nếu yêu cầu là "kiểm tra tất cả bản ghi trước khi cho phép tiếp tục", hãy có **một giai đoạn xác thực được tiêu thụ hết** hoặc một vòng lặp kiểm tra rõ ràng, không chỉ xây một pipeline rồi giả định validation đã hoàn tất.


## 7. Kiểm thử từng hợp đồng thay vì chỉ kiểm thử kết quả cuối

Một pipeline dài thường được kiểm thử qua một bộ dữ liệu mẫu rồi so sánh đầu ra cuối. Điều đó chưa đủ: nếu nhiều bước cùng có lỗi và triệt tiêu nhau, test đầu-cuối vẫn có thể tình cờ vượt qua.

Khi đã tách hàm có tên, hãy thử:

- **`normalizeSale`:** giá trị hợp lệ được chuẩn hóa; `null`, mã trống, trạng thái sai, số âm đều bị từ chối.
- **`paidOnly`:** chỉ những đơn `PAID` còn lại, giữ thứ tự và những giá trị trùng phù hợp.
- **`summarize`:** số lượng và tổng theo khách hàng đúng; khóa cùng tổng được sắp theo mã.
- **`process`:** các bước kết nối đúng với dữ liệu xen kẽ trạng thái và số tiền.
- **Dữ liệu biên:** nguồn rỗng, một phần tử, không đơn nào PAID, nhiều khách cùng tổng, khách có nhiều đơn.
- **Tính không can thiệp:** không sửa nguồn hoặc biến trạng thái gốc; danh sách trả ra không cho sửa cấu trúc theo hợp đồng do ta chọn.

### 7.1. Chương trình kiểm thử Java 8+ tự chứa

Tạo file `NamedPipelineTest.java` cùng thư mục với `NamedPipelineExample.java` ở mục 5:

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class NamedPipelineTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void expectInvalid(
            Runnable action, String message) {
        boolean rejected = false;
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        check(rejected, message);
    }

    public static void main(String[] args) {
        NamedPipelineExample.RawSale raw =
            new NamedPipelineExample.RawSale(
                " O-1 ", " KH-A ", "paid", 1000);

        NamedPipelineExample.Sale normalized =
            NamedPipelineExample.normalizeSale(raw);

        check("O-1".equals(normalized.orderId),
            "orderId chua trim");
        check("KH-A".equals(normalized.customerId),
            "customerId chua trim");
        check("PAID".equals(normalized.status),
            "status chua chuan hoa");
        check(normalized.amountCents == 1000,
            "amountCents bi thay doi");
        check("paid".equals(raw.status),
            "ham normalize da sua du lieu nguon");

        expectInvalid(
            () -> NamedPipelineExample.normalizeSale(null),
            "Phai tu choi ban ghi null");

        expectInvalid(
            () -> NamedPipelineExample.normalizeSale(
                new NamedPipelineExample.RawSale(
                    " ", "KH-A", "PAID", 100)),
            "Phai tu choi orderId trong");

        expectInvalid(
            () -> NamedPipelineExample.normalizeSale(
                new NamedPipelineExample.RawSale(
                    "O-2", null, "PAID", 100)),
            "Phai tu choi customerId null");

        expectInvalid(
            () -> NamedPipelineExample.normalizeSale(
                new NamedPipelineExample.RawSale(
                    "O-2", "KH-A", "UNKNOWN", 100)),
            "Phai tu choi status la");

        expectInvalid(
            () -> NamedPipelineExample.normalizeSale(
                new NamedPipelineExample.RawSale(
                    "O-2", "KH-A", "PAID", -1)),
            "Phai tu choi amount am");

        List<NamedPipelineExample.RawSale> source =
            Arrays.asList(
                raw,
                new NamedPipelineExample.RawSale(
                    "O-2", "KH-B", "PAID", 200),
                new NamedPipelineExample.RawSale(
                    "O-3", "KH-A", "REFUNDED", 5000),
                new NamedPipelineExample.RawSale(
                    "O-4", "KH-A", "PAID", 300)
            );

        List<NamedPipelineExample.Sale> paid =
            NamedPipelineExample.paidOnly(
                NamedPipelineExample.normalize(
                    source.stream()))
            .collect(Collectors.toList());

        check(paid.size() == 3,
            "Bo loc PAID sai so luong");
        check("O-1".equals(paid.get(0).orderId)
                && "O-2".equals(paid.get(1).orderId)
                && "O-4".equals(paid.get(2).orderId),
            "Bo loc PAID sai encounter order");

        List<NamedPipelineExample.CustomerSummary> result =
            NamedPipelineExample.process(source);

        check(result.size() == 2,
            "Sai so nhom khach hang");

        check("KH-A".equals(result.get(0).customerId)
                && result.get(0).totalCents == 1300
                && result.get(0).orderCount == 2,
            "Sai tong/so don KH-A");

        check("KH-B".equals(result.get(1).customerId)
                && result.get(1).totalCents == 200
                && result.get(1).orderCount == 1,
            "Sai tong/so don KH-B");

        List<NamedPipelineExample.CustomerSummary> empty =
            NamedPipelineExample.process(
                Collections.<NamedPipelineExample.RawSale>
                    emptyList());

        check(empty.isEmpty(), "Nguon rong phai tra rong");

        List<NamedPipelineExample.CustomerSummary> noPaid =
            NamedPipelineExample.process(
                Arrays.asList(
                    new NamedPipelineExample.RawSale(
                        "O-8", "KH-A", "PENDING", 77)));

        check(noPaid.isEmpty(),
            "Khong co PAID thi khong co nhom");

        List<NamedPipelineExample.CustomerSummary> tie =
            NamedPipelineExample.process(Arrays.asList(
                new NamedPipelineExample.RawSale(
                    "O-2", "KH-B", "PAID", 100),
                new NamedPipelineExample.RawSale(
                    "O-1", "KH-A", "PAID", 100)));

        check("KH-A".equals(tie.get(0).customerId)
                && "KH-B".equals(tie.get(1).customerId),
            "Thieu tie-breaker khi tong bang nhau");

        boolean unmodifiable = false;
        try {
            result.add(new NamedPipelineExample.CustomerSummary(
                "KH-X", 1, 10));
        } catch (UnsupportedOperationException expected) {
            unmodifiable = true;
        }
        check(unmodifiable,
            "Ket qua process phai unmodifiable");

        expectInvalid(
            () -> NamedPipelineExample.process(
                Arrays.asList(
                    new NamedPipelineExample.RawSale(
                        "O-9", "KH-X", "PAID", 1),
                    new NamedPipelineExample.RawSale(
                        "O-10", "KH-X", "BROKEN", 1))),
            "Phai phat hien ban ghi loi khi tieu thu het");

        System.out.println("PASS: named pipeline contracts");
    }
}
```

Để tự biên dịch và chạy:

```text
javac NamedPipelineExample.java NamedPipelineTest.java
java NamedPipelineExample
java NamedPipelineTest
```

Khi chương trình và các kiểm tra đều đúng, `NamedPipelineTest` in:

```text
PASS: named pipeline contracts
```

Đây là **mẫu kiểm thử tự chạy**, không phải tuyên bố đã thực sự biên dịch trong lúc soạn bài. Test xác nhận các hợp đồng được chọn, không chứng minh mọi dữ liệu có thể xuất hiện trong sản phẩm đều đúng.

### 7.2. Vì sao các kiểm tra này có giá trị?

- Test `normalizeSale` chỉ cần **một bản ghi** để xác định quy tắc.
- Test `paidOnly` kiểm tra cả số lượng và **thứ tự sau lọc**.
- Test `summarize` thông qua `process` xác nhận số lượng nhóm và tổng, không chỉ giá trị dòng đầu.
- Test hòa tổng tiền buộc code có **khóa phụ tăng dần**; nếu thiếu, thứ tự `Map` có thể làm test không ổn định.
- Test dữ liệu không hợp lệ xác nhận **chính sách fail-fast**, thay vì silently drop.
- Test nguồn rỗng xác nhận không tự tạo nhóm giả.
- Test không sửa nguồn và list kết quả xác nhận hợp đồng về trạng thái.

Với hệ thống thực tế, bổ sung test về tràn số nguyên, mã khách hàng có Unicode, dữ liệu rất lớn, số bản ghi trùng mã và các ca đồng thời nếu chúng thuộc yêu cầu nghiệp vụ.

## 8. Cách đặt tên để hợp đồng hiển thị ngay khi đọc code

Một pipeline được tách tốt phải dễ đọc ở lớp orchestration:

```java
List<CustomerSummary> result =
    summarize(paidOnly(normalize(source.stream())));
```

Tên thể hiện luồng: **chuẩn hóa → lọc đã thanh toán → tổng hợp**.

### 8.1. Tên theo nghiệp vụ, không theo chi tiết ngẫu nhiên

| Tên mơ hồ | Tên nên cân nhắc | Lý do |
| --- | --- | --- |
| `step1` | `normalize` | Thể hiện quy tắc, không phải vị trí. |
| `fixData` | `normalizeSale` | Cho biết biến đổi bản ghi gì. |
| `filterData` | `paidOnly` | Cho biết điều kiện lọc. |
| `process2` | `summarize` | Cho biết loại kết quả. |
| `doSomething` | `calculateCustomerTotals` | Diễn đạt ý nghĩa tổng hợp. |
| `check` | `validateStatus` | Nêu điều kiện được kiểm tra. |

Một tên như `paidOnly` phù hợp nếu trạng thái là điều kiện duy nhất. Nếu nghiệp vụ thay đổi thành chỉ nhận đơn vừa thanh toán vừa vượt một ngưỡng tiền, cân nhắc tên `eligibleForRevenue` và ghi hợp đồng mới thay vì bí mật nhét thêm điều kiện vào `paidOnly`.

### 8.2. Chọn chữ ký theo mục đích

Có ba hình thức phổ biến:

```java
// Quy tắc trên một phần tử: thuần, dễ unit test.
static Sale normalizeSale(RawSale raw);

// Bước trung gian: giữ pipeline lazy.
static Stream<Sale> normalize(Stream<RawSale> source);

// Ranh giới tổng hợp: trả kết quả đã materialize.
static List<CustomerSummary> summarize(
    Stream<Sale> paidSales);
```

Nếu một bước cần trả **cả dữ liệu thành công và lỗi**, `Stream<T>` đơn lẻ có thể không phản ánh đầy đủ hợp đồng. Khi đó, hãy thiết kế `ValidationResult`, `Either` hoặc đối tượng kết quả có hai collection rõ ràng, thay vì giấu lỗi trong `peek`.

### 8.3. Có cần viết hàm cho từng `map` và `filter`?

Không nhất thiết:

```java
List<String> names = users.stream()
    .filter(User::isActive)
    .map(User::getName)
    .collect(Collectors.toList());
```

Nếu hai phương thức và ý nghĩa đã rõ, tách thành `activeUsers` và `extractNames` chỉ để rút một dòng có thể làm code khó đọc hơn. Nên tách khi:

- Quy tắc có tên nghiệp vụ rõ ràng.
- Có nhánh hoặc kiểm tra dữ liệu đáng kể.
- Nhiều nơi cần tái sử dụng cùng quy tắc.
- Cần test độc lập một hành vi.
- Cần thay chính sách lỗi mà không chạm toàn pipeline.

Mục tiêu là **ranh giới có ích**, không phải số lượng phương thức.

## 9. Dùng `peek` và log để tìm lỗi, không để thực hiện nghiệp vụ

`peek` là intermediate operation cho phép quan sát phần tử được tiêu thụ ở một vị trí trong pipeline. Nó thường hữu ích để ghi log tạm thời:

```java
List<CustomerSummary> result = summarize(
    paidOnly(
        normalize(source.stream())
            .peek(sale ->
                System.out.println(
                    "Sau normalize: " + sale.orderId))
    )
);
```

Khi chạy với terminal `summarize`, log này giúp xem bản ghi sau chuẩn hóa **trước khi lọc trạng thái**. Để quan sát sau bộ lọc:

```java
Stream<NamedPipelineExample.Sale> paid =
    NamedPipelineExample.paidOnly(
        NamedPipelineExample.normalize(source.stream()));

List<NamedPipelineExample.Sale> snapshot = paid
    .peek(sale -> System.out.println(
        "Sau paidOnly: " + sale.orderId))
    .collect(Collectors.toList());
```

`peek` không nhất thiết được gọi cho từng phần tử nguồn trong **mọi pipeline**. Terminal operation có thể short-circuit và một số phép toán có thể tối ưu hóa, nhất là khi phần tử bị loại hoặc không cần được tính để quyết định kết quả.

### 9.1. Không dùng `peek` để cập nhật trạng thái nghiệp vụ

Sai:

```java
List<String> audit = new ArrayList<>();

long count = source.stream()
    .peek(sale -> audit.add(sale.orderId))
    .count();

// KHÔNG ĐƯỢC suy ra audit chứa toàn bộ mã đơn.
```

Với nguồn có kích thước xác định và `count()`, runtime có thể **không chạy `peek`** nếu không cần duyệt để biết số phần tử. Trong parallel stream, việc thêm vào `ArrayList` chung còn không an toàn.

Nếu yêu cầu là ghi audit đầy đủ, hãy xây dựng một **bước nghiệp vụ tường minh** với chính sách thất bại, độ bền và retry phù hợp. `peek` dùng để **chẩn đoán**, không phải một phần thiết yếu của thuật toán.

### 9.2. Log không nên làm rò dữ liệu nhạy cảm

Trong ứng dụng thật, một bản ghi có thể chứa email, thông tin cá nhân, token hoặc dữ liệu thanh toán. Đừng in nguyên đối tượng hay tiền lương/doanh thu nhạy cảm ra log không kiểm soát.

Ví dụ chỉ ghi **mã đã ẩn một phần** hoặc một số đếm tổng hợp; gắn correlation ID của yêu cầu, mức log phù hợp, và tắt debug quá chi tiết sau khi giải quyết sự cố. Đây cũng là lợi ích của việc có bước tên rõ ràng: log có thể ghi `stage=normalize` thay vì `step=3` mơ hồ.

## 10. Materialize một bước để quan sát: hữu ích nhưng có đánh đổi

Đối với nguồn trong bộ nhớ hữu hạn, có thể **tạm thời** chèn một điểm kết thúc rồi thu kết quả của từng bước:

```java
List<NamedPipelineExample.Sale> normalized =
    NamedPipelineExample.normalize(source.stream())
        .collect(Collectors.toList());

System.out.println("Normalized: " + normalized.size());

List<NamedPipelineExample.Sale> paid =
    NamedPipelineExample.paidOnly(normalized.stream())
        .collect(Collectors.toList());

System.out.println("Paid: " + paid.size());

List<NamedPipelineExample.CustomerSummary> result =
    NamedPipelineExample.summarize(paid.stream());
```

Cách này tạo được ba mốc rõ ràng: **sau chuẩn hóa**, **sau lọc** và **sau tổng hợp**. Bạn có thể dùng debugger kiểm tra số dòng, trường dữ liệu, thứ tự và ví dụ gây lỗi tại mỗi mốc.

Nhưng materialization có chi phí:

| Lợi ích | Chi phí/rủi ro |
| --- | --- |
| Dễ quan sát danh sách của mỗi bước | Tạo collection và tham chiếu trung gian |
| Có thể kiểm tra số lượng/trùng lặp độc lập | Giảm lợi ích lazy, có thể tiêu thụ toàn bộ nguồn |
| Dễ đặt breakpoint trên dữ liệu nhỏ | Không thích hợp cho stream rất lớn/vô hạn |
| Dễ so sánh dữ liệu trước/sau một bước | Thay đổi thời điểm phát sinh lỗi, thời gian và bộ nhớ |
| Dùng được nhiều stream mới từ collection đã thu | Không còn tương đương hoàn toàn với nguồn I/O thay đổi theo thời gian |

**Điểm cốt lõi:** materialize là **kỹ thuật chẩn đoán hoặc ranh giới dữ liệu có chủ đích**, không phải mục tiêu mặc định của refactor. Khi hoàn tất gỡ lỗi, hãy cân nhắc trở về pipeline lazy nếu không có yêu cầu giữ snapshot.

### 10.1. Không nên vật chất hóa nguồn vô hạn

```java
// KHÔNG NÊN: nguồn vô hạn và terminal collect không giới hạn.
// List<Integer> all = Stream.iterate(0, n -> n + 1)
//     .collect(Collectors.toList());
```

Đặt giới hạn rõ hoặc viết phép tổng hợp hữu hạn:

```java
List<Integer> firstTen = Stream.iterate(0, n -> n + 1)
    .limit(10)
    .collect(Collectors.toList());

System.out.println(firstTen); // [0,1,2,3,4,5,6,7,8,9]
```

Với stream I/O, `collect` cũng không tự giải quyết quyền sở hữu tài nguyên; phần sau sẽ làm rõ cách đóng nguồn đúng cách.

## 11. Chọn chính sách lỗi trước khi tách pipeline

Ba chính sách thường gặp:

| Chính sách | Hành vi | Khi thích hợp |
| --- | --- | --- |
| **Fail-fast** | Gặp bản ghi sai thì ném lỗi, không công bố kết quả như thành công | Báo cáo tài chính, dữ liệu phải hoàn toàn hợp lệ |
| **Skip invalid** | Bỏ bản ghi sai và tiếp tục | Nghiệp vụ đã cho phép bỏ với điều kiện có thống kê lỗi |
| **Collect errors** | Thu đồng thời dữ liệu hợp lệ và danh sách lỗi | Nhập file hàng loạt, ETL, kiểm tra chất lượng dữ liệu |

Ví dụ `NamedPipelineExample` chọn **fail-fast**. Thay `normalizeSale` bằng `map` tự bắt mọi lỗi rồi trả `null` và lọc `Objects::nonNull` sẽ âm thầm đổi hợp đồng:

```java
// KHÔNG NÊN nếu nghiệp vụ yêu cầu từ chối dữ liệu lỗi:
source.stream()
    .map(raw -> {
        try {
            return NamedPipelineExample.normalizeSale(raw);
        } catch (IllegalArgumentException ex) {
            return null; // Nuốt lỗi và mất thông tin.
        }
    })
    .filter(Objects::nonNull);
```

Nếu mục tiêu là nhập liệu với lỗi được báo riêng, một vòng lặp **đơn giản, minh bạch** có thể tốt hơn một pipeline cố nhét cả hai luồng kết quả:

```java
List<NamedPipelineExample.Sale> valid =
    new ArrayList<>();
List<String> errors = new ArrayList<>();

int index = 0;

for (NamedPipelineExample.RawSale raw : source) {
    try {
        valid.add(
            NamedPipelineExample.normalizeSale(raw));
    } catch (IllegalArgumentException ex) {
        errors.add(
            "Row " + index + ": " + ex.getMessage());
    }
    index++;
}

System.out.println("Valid: " + valid.size());
System.out.println("Errors: " + errors.size());
```

Đoạn trên minh họa **một chính sách khác** với fail-fast; khi triển khai cần quyết định có dừng nếu quá nhiều lỗi, có che thông tin nhạy cảm trong thông báo lỗi và thứ tự báo lỗi có quan trọng hay không.

Điều quan trọng là **hợp đồng đã được gọi tên**: hàm kiểu `validateAll`, `partitionValidInvalid` hoặc `rejectInvalid` sẽ rõ hơn một `map` bí mật nuốt exception.

### 11.1. Ngoại lệ xảy ra ở lúc nào?

Với một bước lazy:

```java
Stream<NamedPipelineExample.Sale> stage =
    NamedPipelineExample.normalize(
        source.stream());
```

`normalizeSale` chưa nhất thiết chạy. Khi terminal operation tiêu thụ, `IllegalArgumentException` có thể được ném từ một bản ghi không hợp lệ. Nếu pipeline chạy song song và có nhiều bản ghi lỗi, **không nên phụ thuộc bản ghi nào được báo trước**, vì lịch xử lý không được bảo đảm.

Nếu yêu cầu phải báo **tất cả lỗi theo thứ tự dòng**, hãy chạy một lượt xác thực có kiểm soát và lưu danh sách lỗi trước khi tổng hợp, thay vì dựa vào thứ tự exception của parallel stream.

## 12. Chọn ranh giới rõ giữa xử lý và tài nguyên I/O

Một hàm trả `Stream<T>` có thể là hợp đồng tốt khi nguồn là `List`. Nhưng với `Files.lines`, `Files.walk` hoặc một cursor, stream có thể giữ tài nguyên I/O cần đóng.

Sai:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

// KHÔNG NÊN: trả stream đã bị đóng.
static Stream<String> brokenLines(Path path)
        throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.filter(s -> !s.isEmpty());
    }
}
```

Khi hàm trả về, `try-with-resources` đã đóng `lines`. Bên ngoài không thể tiêu thụ pipeline như dự định.

Phương án đúng: **tiêu thụ nguồn ngay trong phạm vi sở hữu tài nguyên**, hoặc chuyển quyền đóng cho bên gọi thông qua API có tài liệu rõ ràng.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> firstNonEmptyLines(Path path)
        throws IOException {

    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {

        return lines
            .filter(s -> !s.trim().isEmpty())
            .limit(10)
            .collect(Collectors.toList());
    }
}
```

Đây là một bước **eager có kiểm soát**: trả list tối đa 10 dòng, đóng nguồn đúng lúc. Lưu ý lỗi I/O có thể phát sinh lúc mở tệp (`IOException`) hoặc trong quá trình duyệt lazy (`UncheckedIOException`). Không gom mọi lỗi thành list rỗng, vì "không có dòng" khác với "không đọc được tệp".

### 12.1. Một phương thức cho phép bên gọi tự đóng

Nếu buộc phải trả stream nguồn I/O, hợp đồng phải ghi rằng bên gọi **sở hữu việc đóng**:

```java
// Ví dụ API với hợp đồng trách nhiệm rõ:
static Stream<String> openLines(Path path)
        throws IOException {
    return Files.lines(path, StandardCharsets.UTF_8);
}

// Bên gọi:
try (Stream<String> lines = openLines(path)) {
    long count = lines
        .filter(s -> !s.trim().isEmpty())
        .count();
}
```

Trong ứng dụng dịch vụ, có thể ưu tiên API nhận callback để giữ phạm vi đóng tập trung. Dù chọn kiểu nào, việc tách pipeline thành bước có tên **không được làm mất trách nhiệm giải phóng nguồn**.


## 13. Thứ tự, grouping và cardinality phải là một phần của hợp đồng

Khi tách pipeline, không nên ghi chung chung "bước này giữ nguyên dữ liệu". Cần chỉ rõ **bao nhiêu phần tử đi vào, bao nhiêu phần tử có thể đi ra**, cũng như thứ tự đầu ra.

| Thao tác | Quan hệ số phần tử | Ghi chú về thứ tự |
| --- | --- | --- |
| `map` | Một-một nếu không có ngoại lệ | Giữ thứ tự logic nếu nguồn ordered. |
| `filter` | Tối đa một cho mỗi đầu vào | Giữ thứ tự tương đối của những phần tử còn lại. |
| `flatMap` | Không, một hoặc nhiều cho mỗi đầu vào | Phụ thuộc thứ tự nguồn và các stream con. |
| `distinct` | Không làm tăng số phần tử | Với ordered stream giữ lần xuất hiện đầu theo `equals`. |
| `sorted` | Bảo toàn số phần tử | Tạo thứ tự theo comparator. |
| `skip` / `limit` | Loại/bớt theo số lượng | Phụ thuộc encounter order nếu nguồn ordered. |
| `groupingBy` | Nhiều phần tử thành các nhóm | Không cam kết thứ tự duyệt khóa map mặc định. |
| `summarize` của bài | Nhiều đơn thành một dòng/khách | Sắp xếp tổng giảm dần, khách tăng dần khi hòa. |

### 13.1. Đừng coi `Map` là danh sách có thứ tự

Ví dụ:

```java
Map<String, Long> totals = sales.stream()
    .collect(Collectors.groupingBy(
        sale -> sale.customerId,
        Collectors.summingLong(
            sale -> sale.amountCents)));
```

Mã minh họa giả định `sales` là `Stream<Sale>` với các trường tương ứng. `groupingBy` trả `Map`; không dựa vào thứ tự `totals.entrySet()` để nói khách hàng nào đứng đầu.

Nếu báo cáo yêu cầu "doanh thu lớn nhất trước", phải sắp xếp dựa trên **giá trị tổng** sau khi nhóm. Comparator cần **khóa phụ** khi tổng bằng nhau để kết quả kiểm thử có tính xác định.

### 13.2. Phân biệt "không có dữ liệu" với "lỗi tính toán"

Trên nguồn rỗng, `groupingBy` trả một map rỗng và `summarize` trả list rỗng. Đó là **kết quả hợp lệ**.

Ngược lại, khi `normalizeSale` gặp một bản ghi `null` và ném `IllegalArgumentException`, không được diễn giải lỗi thành "không có doanh thu". Hai trạng thái này có ý nghĩa nghiệp vụ khác nhau và cần test riêng.

### 13.3. Đừng bỏ qua ràng buộc trùng mã đơn

Ví dụ tổng hợp hiện tại tính **mỗi bản ghi PAID là một đơn**, chưa loại đơn trùng `orderId`. Nếu một file chứa hai dòng cùng mã, tổng và số đếm có thể bị nhân đôi. Đây không phải lỗi ngẫu nhiên của `groupingBy` mà là **một hợp đồng chưa được bổ sung**.

Nếu nghiệp vụ yêu cầu mỗi `orderId` duy nhất, hãy đặt một bước `rejectDuplicateOrderIds` hoặc `deduplicateById` có chính sách rõ:

- Với trùng mã, báo lỗi hay chọn bản ghi nào?
- Nếu hai dòng có cùng mã nhưng số tiền khác, có được bỏ một dòng không?
- Thứ tự gặp có quyết định bản ghi được giữ hay không?
- Cần bộ nhớ để theo dõi những mã đã thấy không?

**Không tự dùng `distinct()` để giải quyết** nếu `Sale` chưa định nghĩa `equals`/`hashCode` theo nghiệp vụ, hoặc nếu yêu cầu là bắt lỗi chứ không loại trùng. Một bước trùng mã có thể cần cấu trúc `Set` và được thiết kế cẩn thận trước khi chạy song song.

## 14. Hợp đồng của bước có thay đổi khi gọi `parallel()` không?

Một pipeline được tách thành các hàm có tên **không mặc định an toàn hơn khi chạy song song**. Tính đúng vẫn phụ thuộc:

- Những callback **stateless** và **non-interfering**.
- Phép tổng hợp và `combiner` đáp ứng hợp đồng.
- Nguồn, trạng thái và collector phù hợp với cách chia.
- Các yêu cầu về encounter order được thực thi qua phép toán có bảo đảm thứ tự.

Trong ví dụ:

```java
List<NamedPipelineExample.CustomerSummary> parallel =
    NamedPipelineExample.summarize(
        NamedPipelineExample.paidOnly(
            NamedPipelineExample.normalize(
                source.parallelStream())));
```

`normalizeSale` tạo đối tượng mới, không thay đổi dữ liệu gốc. `paidOnly` chỉ kiểm tra status. `Collectors.groupingBy` với `summarizingLong` có combiner do collector chuẩn cung cấp. Kết quả cuối được sắp xếp, nên **có thể** nhận cùng kết quả như chạy tuần tự trong miền số đã xác định. Điều đó **không khẳng định chạy nhanh hơn** hoặc đồng nghĩa mọi cải tiến về sau đều an toàn.

### 14.1. Test tính đúng tuần tự và song song

```java
List<NamedPipelineExample.CustomerSummary> sequential =
    NamedPipelineExample.process(source);

List<NamedPipelineExample.CustomerSummary> parallel =
    NamedPipelineExample.summarize(
        NamedPipelineExample.paidOnly(
            NamedPipelineExample.normalize(
                source.parallelStream())));

if (sequential.size() != parallel.size()) {
    throw new AssertionError("Khac so nhom");
}

for (int i = 0; i < sequential.size(); i++) {
    NamedPipelineExample.CustomerSummary a =
        sequential.get(i);
    NamedPipelineExample.CustomerSummary b =
        parallel.get(i);

    if (!a.customerId.equals(b.customerId)
            || a.orderCount != b.orderCount
            || a.totalCents != b.totalCents) {
        throw new AssertionError(
            "Khac ket qua o vi tri " + i);
    }
}
```

Ví dụ có thể đặt vào một phương thức kiểm thử Java 8+ cùng package với `NamedPipelineExample`. Chúng ta so sánh **giá trị trường**, vì `CustomerSummary` trong mã mẫu không override `equals`. Không dùng `==` để so sánh object kết quả.

### 14.2. Những thay đổi nhỏ có thể phá hợp đồng

Sai:

```java
List<String> seen = new ArrayList<>();

Stream<NamedPipelineExample.Sale> stage =
    NamedPipelineExample.normalize(
        source.parallelStream())
    .peek(sale -> seen.add(sale.orderId));
```

`ArrayList` không an toàn khi nhiều thread cùng ghi, và `peek` không bảo đảm được gọi cho mọi phần tử. Đây không phải cách duy trì nhật ký nghiệp vụ hoặc đếm đơn.

Tương tự, đổi `summarize` thành `reduce` sửa một `HashMap` chung bằng side effect có thể gây race condition. Dùng collector chuẩn hoặc thiết kế collector với supplier/accumulator/combiner hợp lệ thay vì dùng một biến tích lũy bên ngoài.

### 14.3. Thứ tự ngoại lệ có thể khác

Nếu có nhiều dòng sai, parallel stream có thể phát hiện một dòng lỗi không phải dòng đầu theo encounter order. Vì vậy, để thông báo lỗi theo thứ tự file, nên **tách một lượt xác thực tuần tự** hoặc thu toàn bộ lỗi có thứ tự trước khi xử lý song song những bản ghi hợp lệ.

**Tóm lại:** tính đúng ở chế độ tuần tự là điều kiện cần, không phải bằng chứng đủ cho song song. Test cả hai khi dự án thực sự dùng `parallel()`, và đo hiệu năng độc lập.

## 15. Dùng một thuật toán tham chiếu độc lập để kiểm chứng

Một cách tránh sai sót là so kết quả pipeline với **vòng lặp tham chiếu** trên tập nhỏ. Không nên viết test mà chính expected cũng gọi lại toàn bộ `normalize`, `paidOnly` và `summarize`: nếu một quy tắc sai ở cả hai phía, test có thể không phát hiện.

Ví dụ độc lập cho tổng tiền (giả định dữ liệu đã được chuẩn hóa và không tràn `long`):

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Long> expected = new HashMap<>();

for (NamedPipelineExample.Sale sale : normalizedSales) {
    if (!"PAID".equals(sale.status)) {
        continue;
    }

    Long old = expected.get(sale.customerId);
    long newTotal = (old == null ? 0L : old)
        + sale.amountCents;

    expected.put(sale.customerId, newTotal);
}
```

Giờ so từng tổng với kết quả `summarize` thay vì chỉ so số nhóm. Vòng lặp tham chiếu cũng có thể sai, nhưng hai cách viết khác nhau giúp giảm nguy cơ **chia sẻ cùng một lỗi triển khai**.

### 15.1. Những thuộc tính (*properties*) đáng kiểm chứng

Với dữ liệu hợp lệ, tổng không tràn, chính sách "chỉ PAID":

1. **Không phát sinh khách hàng giả:** mọi `customerId` trong kết quả phải có ít nhất một đơn PAID ở đầu vào.
2. **Số đơn:** tổng `orderCount` của các nhóm bằng số dòng PAID.
3. **Tổng tiền:** tổng `totalCents` của các nhóm bằng tổng `amountCents` của dòng PAID.
4. **Bảo toàn phần tử khi chuẩn hóa:** nếu không có lỗi, `normalize` không làm mất hoặc nhân đôi dòng.
5. **Lọc không nhân đôi:** `paidOnly` không làm tăng số dòng.
6. **Đầu ra có thứ tự:** hai nhóm liên tiếp phải thỏa comparator đã công bố.
7. **Không phụ thuộc nguồn đầu vào theo thứ tự:** nếu chỉ yêu cầu tổng theo khách và kết quả được sort, việc tráo thứ tự dòng hợp lệ không được thay đổi **giá trị báo cáo**.
8. **Không can thiệp:** dữ liệu thô không bị sửa bởi pipeline.

Cần tránh property giả: "mọi thay đổi thứ tự đầu vào đều không ảnh hưởng kết quả" **không đúng với mọi Stream**. Các phép `findFirst`, `limit` hay nối chuỗi có thể chủ ý phụ thuộc thứ tự; mỗi bước phải ghi hợp đồng riêng.

### 15.2. Những ca kiểm thử đáng có

| Ca | Đầu vào | Kết quả/chính sách |
| --- | --- | --- |
| Nguồn rỗng | `[]` | Trả list rỗng. |
| Một đơn PAID | Một bản ghi hợp lệ | Một nhóm, count 1, đúng tiền. |
| Không có PAID | Chỉ PENDING/REFUNDED | Trả list rỗng. |
| Trộn trạng thái | PAID và REFUNDED | Chỉ tính PAID. |
| Khoảng trắng/case | Mã có space, `paid` | Chuẩn hóa theo hợp đồng. |
| Dữ liệu lỗi | `null`, mã rỗng, status lạ | Ném `IllegalArgumentException`. |
| Tổng hòa | Hai khách cùng tổng | Sort theo mã phụ. |
| Mã đơn trùng | Hai dòng cùng mã | Theo chính sách doanh nghiệp; mẫu hiện tại **chưa tự loại trùng**. |
| Ngưỡng số | Tổng gần `Long.MAX_VALUE` | Thiết kế kiểm tra tràn nếu nghiệp vụ yêu cầu. |
| Parallel | Nguồn đủ lớn, dữ liệu hợp lệ | Kết quả bằng tuần tự theo hợp đồng. |

Với test dữ liệu sinh ngẫu nhiên, hãy **giữ seed tái lập** và lưu trường hợp nhỏ nhất gây lỗi, thay vì chỉ in "random test failed". Điều đó giúp tái hiện lỗi và xác định bước vi phạm hợp đồng.

## 16. Refactor pipeline dài theo quy trình có kiểm soát

Một quy trình thực tế nên thực hiện theo thứ tự:

### Bước 1 — Đóng băng hành vi hiện tại bằng kiểm thử

Lấy một bộ dữ liệu đại diện có cả trạng thái bình thường và dữ liệu biên. Ghi lại **hành vi cần giữ**, không nhất thiết giữ những lỗi không mong muốn.

Nếu kết quả hiện tại chưa rõ đúng/sai, ghi rõ các giả định nghiệp vụ chưa được xác nhận. Refactor cấu trúc code không tự quyết định chính sách null, hoàn tiền hoặc loại trùng.

### Bước 2 — Xác định ranh giới dựa trên kiểu và trách nhiệm

Đọc pipeline và đánh dấu các vùng:

```text
input
  → parse/validate
  → normalize
  → filter
  → enrich/map
  → group/reduce
  → sort/present
  → output
```

Không nhất thiết pipeline nào cũng cần đủ các bước; chỉ tách những ranh giới tồn tại thật.

### Bước 3 — Viết hợp đồng cho mỗi vùng

Ghi kiểu dữ liệu, điều kiện lỗi, thứ tự và số phần tử. Ví dụ:

```text
normalizeSale:
  input  : RawSale khác null
  output : Sale với mã đã trim và status uppercase
  error  : IllegalArgumentException nếu dữ liệu thiếu/sai
  order  : không áp dụng ở cấp một phần tử
  effect : không sửa RawSale

paidOnly:
  input  : Stream<Sale> đã chuẩn hóa
  output : Stream<Sale> chỉ PAID
  order  : giữ encounter order nếu nguồn ordered
  effect : không sửa Sale
```

### Bước 4 — Trích hàm nhỏ nhất trước

Bắt đầu bằng hàm xử lý một phần tử như `normalizeSale`, vì dễ kiểm thử nhất. Sau đó mới đặt tên cho những nhóm thao tác stream như `paidOnly`. Tránh đổi đồng thời chính sách lỗi và thuật toán tổng hợp nếu mục tiêu ban đầu chỉ là làm rõ cấu trúc.

### Bước 5 — Tách điểm terminal rõ ràng

Đảm bảo người đọc biết đâu là bước vẫn lazy, đâu là bước tiêu thụ `Stream`. Một phương thức tên `summarize` trả `List` hoặc `Map` là ranh giới rõ hơn một phương thức vừa trả stream vừa âm thầm gọi nhiều terminal operation.

### Bước 6 — Chạy lại kiểm thử và đối chiếu metadata

Kiểm tra những bất biến về số dòng, tổng tiền, thứ tự và ngoại lệ. Nếu có sử dụng `parallel`, đối chiếu thêm chế độ đó.

### Bước 7 — Đo hiệu năng khi cần, rồi bỏ dụng cụ debug tạm

Sau refactor, nhiều hàm nhỏ **không nhất thiết** khiến pipeline chạy chậm; JIT và Stream runtime có thể tối ưu các lời gọi. Nhưng materialize quá nhiều list, thêm `sorted` không cần thiết hoặc ghi log trên mỗi bản ghi có thể gây chậm đáng kể.

Không quyết định dựa vào cảm giác "nhiều hàm nên chậm". Hãy benchmark workload đại diện, warm-up phù hợp, cân nhắc JMH và phân biệt chi phí tính toán thực với chi phí nguồn I/O.

## 17. Thực hành một lỗi khó: đếm đúng nhưng danh sách debug rỗng

Giả sử developer thêm log vào `map`:

```java
List<String> visited = new ArrayList<>();

long count = source.stream()
    .map(sale -> {
        visited.add(sale.orderId);
        return sale;
    })
    .count();

System.out.println(count);
System.out.println(visited.size());
```

Với nguồn `List` có kích thước biết trước, `count()` có thể tối ưu mà không chạy mapper, vì `map` không thay đổi số phần tử. Khi đó `count` đúng bằng kích thước nguồn nhưng `visited` có thể rỗng.

### 17.1. Cách chẩn đoán đúng

Hãy xác định mục đích:

- Nếu cần **đếm phần tử**, chỉ gọi `source.size()` hoặc `source.stream().count()`.
- Nếu cần **biến đổi rồi lấy kết quả**, dùng `map(...).collect(Collectors.toList())` và kiểm tra kết quả.
- Nếu cần **bắt buộc xử lý từng bản ghi vì nghiệp vụ**, hãy viết một bước thao tác có hợp đồng tường minh, không gắn side effect vào `map` hoặc `peek` rồi kết thúc bằng `count`.

Ví dụ để kiểm tra dữ liệu đã chuẩn hóa:

```java
List<NamedPipelineExample.Sale> checked =
    NamedPipelineExample.normalize(source.stream())
        .collect(Collectors.toList());

System.out.println(checked.size());
```

`collect` vào list cần thu giá trị trả về của từng phần tử hợp lệ, nên thích hợp hơn một `map` chỉ dùng để cập nhật `visited`. Tuy nhiên, vẫn không nên đặt side effect bắt buộc trong mapper; `normalizeSale` của bài nên trả đối tượng mới và không can thiệp nguồn.

### 17.2. Với `findFirst` và `anyMatch`

Các terminal operation này có thể kết thúc **trước khi duyệt hết nguồn**:

```java
boolean anyPaid = source.stream()
    .map(NamedPipelineExample::normalizeSale)
    .anyMatch(sale -> "PAID".equals(sale.status));
```

Kết quả `anyPaid` chỉ xác nhận **có ít nhất một** đơn PAID trong phần dữ liệu đủ để xác định kết quả. Nó **không xác nhận** mọi dòng còn lại đã được chuẩn hóa, kiểm tra lỗi hay ghi log.

Nếu hợp đồng là "mọi dòng phải hợp lệ", phải xác thực toàn bộ trước; không dùng `anyMatch` để xác nhận điều kiện toàn tập.

## 18. Những lỗi thiết kế và biện pháp khắc phục

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tách pipeline thành `step1`, `step2`, `step3` | Không tăng tính tự mô tả | Đặt tên theo trách nhiệm nghiệp vụ. |
| Một hàm vừa validate, log, lọc, tổng hợp | Khó test và thay đổi chính sách | Tách quy tắc một bản ghi, bước lazy, terminal. |
| Chỉ viết comment, không có test biên | Hợp đồng dễ bị vi phạm khi refactor | Thêm test null, rỗng, status, hòa thứ tự. |
| Dùng `filter(Objects::nonNull)` để nuốt lỗi không báo | Mất bản ghi âm thầm | Chọn fail-fast hoặc collect errors rõ ràng. |
| Gọi `count` rồi dùng lại cùng `Stream` | `IllegalStateException` | Tạo stream mới hoặc materialize có chủ đích. |
| Gọi `normalize` rồi nghĩ toàn bộ đã validate | Intermediate operation lazy | Tiêu thụ bằng terminal phù hợp khi cần kiểm tra hết. |
| Đặt tác dụng phụ trong `peek`/`map` | Callback có thể bị bỏ qua hoặc chạy khác thứ tự | Dùng kết quả trả về hoặc bước nghiệp vụ riêng. |
| Thu tất cả intermediate list chỉ để tiện debug | Tăng bộ nhớ, đổi thời điểm xử lý | Dùng khi cần chẩn đoán, tránh giữ lâu trên dữ liệu lớn. |
| Grouping xong dựa vào thứ tự `Map` | Kết quả không ổn định | Sắp xếp với comparator và tie-breaker. |
| Dùng `distinct()` để bắt trùng mã đơn | Có thể bỏ dữ liệu sai chính sách | Định nghĩa khóa, xử lý lỗi trùng rõ ràng. |
| `reduce` với mutable identity dùng chung | Sai kết quả khi song song | Dùng collector hợp lệ hoặc accumulator không chia sẻ. |
| `parallel` và bộ đếm/list ngoài lambda | Race condition, thứ tự không xác định | Hàm stateless, collector chuẩn, test song song. |
| Ghi log toàn bộ bản ghi nhạy cảm | Rò rỉ dữ liệu và chậm | Log có kiểm soát, ẩn trường nhạy cảm. |
| Trả stream ra ngoài `try-with-resources` | Stream bị đóng trước khi dùng | Tiêu thụ bên trong hoặc chuyển quyền đóng rõ ràng. |
| Bỏ qua `UncheckedIOException` từ nguồn lazy | Tưởng nguồn không có dữ liệu | Phân biệt lỗi I/O với tập rỗng. |
| Tổng tiền kiểu `long` có thể tràn | Báo cáo sai số mà không báo lỗi | Xác định miền, dùng addExact/BigInteger khi cần. |
| Lặp lại toàn pipeline để tính nhiều metadata | Tốn CPU/I/O, có thể không nhất quán | Dùng snapshot hoặc thiết kế tổng hợp một lần khi phù hợp. |
| Dùng `Stream.toList()` trong ví dụ Java 8 | Không biên dịch với Java 8 | Dùng `collect(Collectors.toList())` trong mẫu Java 8. |

## 19. Bài tập thực hành

### Bài 1 — Xác định ranh giới

Cho pipeline:

```java
List<String> result = names.stream()
    .filter(s -> s != null)
    .map(String::trim)
    .filter(s -> !s.isEmpty())
    .map(String::toUpperCase)
    .distinct()
    .sorted()
    .collect(Collectors.toList());
```

Hãy đề xuất hai hoặc ba hàm có tên phản ánh nhóm quy tắc. Nêu dữ liệu vào/ra, thứ tự và chính sách `null`.

### Bài 2 — Đặt hợp đồng cho bộ lọc

Viết `paidOnly(Stream<Sale>)` theo yêu cầu chỉ giữ trạng thái `PAID`. Có nên kiểm tra null/trạng thái lạ ở đây hay đã thuộc `normalizeSale`? Giải thích.

### Bài 3 — Kiểm tra dữ liệu rỗng

Với danh sách không chứa đơn PAID, `process` nên trả gì? Có cần tạo một `CustomerSummary` với tổng bằng 0 cho mọi khách từng xuất hiện không?

### Bài 4 — Kết quả có thứ tự xác định

Hai khách có tổng tiền bằng nhau. Vì sao chỉ sắp xếp giảm dần theo tổng tiền chưa đủ cho báo cáo ổn định? Viết comparator có khóa phụ.

### Bài 5 — Bẫy của `peek`

`source.stream().peek(logAction).count()` có bảo đảm `logAction` được gọi cho mọi phần tử không? `parallel()` có làm mọi log xuất hiện theo thứ tự nguồn không?

### Bài 6 — Tránh tiêu thụ Stream hai lần

Bạn cần cả `count` và `List` sau bước chuẩn hóa trên một `List<RawSale>` hữu hạn. Đề xuất một cách làm không dùng lại stream đã tiêu thụ và nêu đánh đổi về bộ nhớ.

### Bài 7 — Phát hiện chính sách lỗi

Vì sao bắt `IllegalArgumentException` trong `map`, trả `null` rồi thêm `filter(Objects::nonNull)` có thể làm sai hợp đồng fail-fast? Nếu cần thu lỗi theo từng dòng, dùng cách nào?

### Bài 8 — I/O và vòng đời

Một hàm `openLines(Path)` trả `Files.lines(path)`. Ai đóng stream? Vì sao không nên mở `Files.lines` trong một khối try rồi trả lại stream để bên ngoài đọc?

### Bài 9 — Tính đúng khi song song

Nếu `normalizeSale` được sửa để tăng một biến `static int counter` trong mỗi lần gọi, có thể gây vấn đề gì khi chạy `parallel()`? Dùng giải pháp gì nếu mục tiêu chỉ là đếm các bản ghi PAID?

### Bài 10 — Thiết kế thêm bước kiểm tra trùng mã

Nghiệp vụ không cho phép hai đơn có cùng `orderId` trong một báo cáo. Hãy đặt tên bước mới, ghi rõ chính sách lỗi, vị trí của bước trong pipeline và đề xuất cách kiểm thử.

## 20. Đáp án và gợi ý

**Bài 1.** Có thể tạo `normalizeNames(Stream<String>)` để loại null, trim, loại chuỗi trống và uppercase, rồi `uniqueSortedNames(Stream<String>)` để `distinct` và `sorted`. Hoặc tách `normalizeName(String)` cho quy tắc trên một chuỗi và định nghĩa hợp đồng null rõ ràng. Nhớ rằng nếu loại null bằng filter thì chính sách là **skip invalid**, không phải fail-fast.

**Bài 2.** Nếu có một giai đoạn chuẩn hóa/validate độc lập, `paidOnly` nên chỉ giữ `"PAID".equals(sale.status)` và không lặp lại tất cả quy tắc. Nếu đầu vào có thể đến từ caller khác không được bảo đảm hợp lệ, cần viết rõ tiền điều kiện hoặc kiểm tra ở ranh giới API.

**Bài 3.** `process` trả list rỗng theo hợp đồng của bài, vì chỉ tổng hợp đơn PAID. Tạo nhóm 0 cho khách chưa có đơn PAID là nghiệp vụ khác và cần nguồn danh sách khách hàng riêng.

**Bài 4.**

```java
Comparator<CustomerSummary> cmp =
    Comparator.comparingLong(
            (CustomerSummary s) -> s.totalCents)
        .reversed()
        .thenComparing(s -> s.customerId);
```

Comparator mẫu đặt trong phạm vi có kiểu `CustomerSummary`. Khóa phụ giúp thứ tự tổng khi hai khách có cùng số tiền.

**Bài 5.** Không. `peek` có thể không được đánh giá nếu `count` suy được kích thước nguồn. Khi song song, thứ tự log càng không được cam kết. Dùng logging chẩn đoán, không dùng làm audit bắt buộc.

**Bài 6.** Trước hết thu `List<Sale> normalized = normalize(source.stream()).collect(Collectors.toList());`, sau đó lấy `long count = normalized.size();` và tái sử dụng list. Đổi lại sẽ materialize toàn bộ dữ liệu, tốn bộ nhớ theo kích thước nguồn và làm mất lợi ích lazy đối với dữ liệu rất lớn.

**Bài 7.** Hành vi ấy biến lỗi thành bản ghi bị mất, khiến báo cáo trông hợp lệ nhưng thiếu dữ liệu. Nếu nghiệp vụ chọn fail-fast thì để exception đi qua. Nếu chọn collect errors, duyệt tất cả dòng và thu riêng danh sách bản ghi hợp lệ cùng các lỗi có chỉ số, có thể dùng vòng lặp hoặc đối tượng kết quả chuyên dụng.

**Bài 8.** Bên gọi `openLines` phải đóng bằng `try (Stream<String> lines = openLines(path)) { ... }` nếu API chuyển quyền sở hữu. Trả stream từ trong try của chính hàm mở là sai vì try kết thúc trước khi bên ngoài tiêu thụ.

**Bài 9.** `static int counter` không có đồng bộ hóa có thể bị race condition; ngay cả `AtomicInteger` cũng không khiến số thứ tự tương ứng encounter order. Nếu chỉ cần đếm đơn PAID, dùng `normalize(...).filter(...).count()` trên nguồn phù hợp; không đếm bằng side effect trong mapper.

**Bài 10.** Đặt `rejectDuplicateOrderIds` sau bước chuẩn hóa để so mã đã trim, trước `paidOnly` nếu chính sách kiểm tra trùng áp dụng **toàn bộ nguồn**, hoặc sau `paidOnly` nếu chỉ quan tâm trùng trong đơn PAID. Hợp đồng: nếu phát hiện mã trùng, ném lỗi có thông tin phù hợp; nếu không, bảo toàn đầy đủ dữ liệu và thứ tự. Test với mã trùng, mã khác nhau, mã có khoảng trắng, nguồn rỗng và trạng thái xen kẽ. Nếu dùng `Set` lưu mã đã thấy, hãy tránh predicate có trạng thái chia sẻ trong parallel stream; chọn một bước kiểm tra tách biệt có kiểm soát.

## 21. Checklist áp dụng khi refactor pipeline

- [ ] Đã xác định trách nhiệm thật sự của từng stage, không chỉ tách theo số dòng.
- [ ] Tên hàm thể hiện **quy tắc nghiệp vụ**, tránh `step1` hoặc `doWork`.
- [ ] Kiểu đầu vào/đầu ra của từng stage rõ ràng, tránh dùng `Object` không cần thiết.
- [ ] Có tiền điều kiện và hậu điều kiện về `null`, chuỗi trống, số âm, trạng thái.
- [ ] Có chính sách lỗi tường minh: fail-fast, skip invalid hay collect errors.
- [ ] Đã ghi quy tắc về **cardinality** và encounter order.
- [ ] Những hàm biến đổi phần tử thuần và có unit test trực tiếp.
- [ ] Có test cho bước lọc và tổng hợp, không chỉ test đầu-cuối.
- [ ] Bước grouping có sắp xếp rõ ràng nếu đầu ra yêu cầu thứ tự.
- [ ] Có ca kiểm thử hòa tiêu chí, dữ liệu rỗng, không match và dữ liệu sai.
- [ ] Không dùng lại một `Stream` sau terminal operation.
- [ ] Không dựa vào `peek`/`map` có side effect để bảo đảm mọi bản ghi được xử lý.
- [ ] Không vật chất hóa mọi bước trên nguồn vô hạn hoặc rất lớn.
- [ ] Nếu có nguồn I/O, quyền sở hữu `close` được mô tả và thực hiện đúng.
- [ ] Dữ liệu không bị sửa trong lúc pipeline đang duyệt nếu nguồn không hỗ trợ concurrency.
- [ ] `reduce`/`collect` có hợp đồng phù hợp khi chạy song song.
- [ ] Đã phân biệt tính đúng và hiệu năng; chỉ tối ưu sau khi có phép đo.
- [ ] Các ví dụ dùng API tương thích với mức Java mục tiêu.

## 22. Tổng kết

Một pipeline dễ bảo trì cần rõ **dữ liệu đi qua những quy tắc nào**, và **quy tắc nào đang được kiểm tra**:

```text
RawSale
   |
 normalizeSale / normalize
   |       (kiểm tra và chuẩn hóa, có thể lỗi)
   v
 Sale
   |
 paidOnly
   |       (lọc theo trạng thái PAID)
   v
 Stream<Sale>
   |
 summarize
   |       (grouping + count/sum + sort)
   v
 List<CustomerSummary>
```

Từ đó, hãy giữ các nguyên tắc:

1. **Một tên — một trách nhiệm:** đặt tên stage theo ngữ nghĩa nghiệp vụ.
2. **Hợp đồng có thể kiểm chứng:** nêu tiền điều kiện, hậu điều kiện, xử lý lỗi, số phần tử, thứ tự và side effect.
3. **Giữ lazy đúng chỗ:** hàm trả `Stream` thường chỉ xây pipeline; hàm terminal tạo kết quả hữu hình.
4. **Test theo lớp:** unit test quy tắc từng bản ghi, test step, test end-to-end, kiểm chứng bằng nguồn tham chiếu khi hữu ích.
5. **Dùng debug có chủ đích:** `peek` để quan sát, không thực hiện hành động nghiệp vụ; materialize khi cần chẩn đoán và hiểu chi phí.
6. **Tránh lỗi tài nguyên và trạng thái:** không tái sử dụng stream đã tiêu thụ, không để lọt stream I/O ra ngoài phạm vi đóng, không sửa nguồn trong pipeline.
7. **Giữ ngữ nghĩa khi tối ưu:** grouping và sorting phải có thứ tự rõ; parallel không chữa được các hàm có side effect hoặc phép gộp sai.

Tách pipeline dài thành **các bước có tên và hợp đồng rõ ràng** không chỉ giúp code ngắn gọn hơn ở lớp điều phối; quan trọng hơn, nó giúp bạn nhìn thấy điểm dữ liệu thay đổi, thiết kế kiểm thử đáng tin cậy, chẩn đoán nhanh vấn đề và mở rộng Java Stream API mà không làm lệch quy tắc nghiệp vụ.
