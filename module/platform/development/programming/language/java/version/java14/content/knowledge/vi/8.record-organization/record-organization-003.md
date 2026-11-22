# Record cục bộ cho dữ liệu trung gian trong phương thức

## Mục tiêu

Khi xử lý dữ liệu, một phương thức thường cần một **giá trị trung gian gồm nhiều thành phần**: mã sản phẩm kèm tổng tiền và mức ưu tiên, khóa ghép gồm kho hàng và mã sản phẩm, hoặc một nhóm số liệu tạm dùng trong một pipeline. Nếu kiểu dữ liệu đó **chỉ có ý nghĩa bên trong một khối lệnh**, Java cho phép khai báo **local record class** (record cục bộ) ngay tại đó.

Bài học tập trung vào cách dùng **record cục bộ để tổ chức dữ liệu trung gian trong phương thức** mà không đưa một kiểu chỉ phục vụ nội bộ lên cấp lớp/package.

Sau bài này, bạn có thể:

- Khai báo và sử dụng `record` ngay trong thân phương thức, hiểu phạm vi tên kiểu và vòng đời đối tượng.
- Dùng local record làm **giá trị trung gian trong Stream** hoặc **khóa ghép của `Map`**, tận dụng các accessor, `equals`, `hashCode` và `toString` được tạo tự động.
- Giải thích vì sao local record **ngầm định `static`** và không thể truy cập trực tiếp biến cục bộ, tham số phương thức hay trạng thái instance bên ngoài nó.
- Áp dụng constructor, kiểm tra dữ liệu và các giới hạn về tính bất biến của record.
- Lựa chọn hợp lý giữa **local record**, **member record**, một kiểu domain dùng chung hoặc biến cục bộ đơn giản.
- Biên dịch/chạy ví dụ Java 17 có kết quả xác định.

**Phiên bản áp dụng:** `record` được thử nghiệm trong Java 14 và trở thành tính năng chuẩn ở **Java 16** theo [JEP 395](https://openjdk.org/jeps/395). Cú pháp trong bài sử dụng **Java 17 trở lên**, không cần `--enable-preview`. Điều này cũng đáp ứng yêu cầu chỉ dùng kiến thức Java còn áp dụng hiện nay.

## 1. Local record là gì?

Một record thông thường:

~~~java
record Position(int row, int column) {}
~~~

định nghĩa một lớp dữ liệu với hai components. Java tự cung cấp:

- Hai component fields kiểu `private final`.
- Accessor `row()` và `column()`.
- Canonical constructor nhận các components theo thứ tự khai báo.
- `equals(Object)` và `hashCode()` dựa trên các components.
- `toString()` để biểu diễn các components dưới dạng văn bản.

**Local record** vẫn có đặc tính này, nhưng được **khai báo trực tiếp trong một block**, thường là thân phương thức:

~~~java
import java.util.List;

class Example {
    static int sumPrices(List<Integer> prices) {
        record PriceLine(int index, int value) {}

        PriceLine first = new PriceLine(0, prices.get(0));
        return first.value();
    }
}
~~~

Đây là **đoạn minh họa cú pháp**: giả định `prices` không null và chứa ít nhất một phần tử; mục đích là cho thấy `record PriceLine(...)` nằm trong `sumPrices`. Với phép tính đơn giản đến mức chỉ cần một biến, thực tế **không nên tạo record dư thừa**. Local record có giá trị nhất khi một bản ghi trung gian gồm **nhiều trường liên quan**.

Tên `PriceLine` chỉ có thể được tham chiếu trong phạm vi khai báo hợp lệ của block đó. Một phương thức khác không thể viết chữ ký trả về `PriceLine` vì tên kiểu không nằm trong phạm vi của nó.

**Cần phân biệt phạm vi tên với vòng đời object:** đối tượng tạo từ local record vẫn là đối tượng Java bình thường trên heap và có thể sống lâu hơn lời gọi phương thức nếu được tham chiếu qua một interface hoặc `Object`. Từ “cục bộ” mô tả **vị trí khai báo và phạm vi sử dụng tên kiểu**, không có nghĩa JVM tự hủy object ngay khi phương thức kết thúc.

## 2. Khi nào record cục bộ giúp mã sáng sủa hơn?

### 2.1. Thay một “tuple” không có tên cho các trường

Hãy tưởng tượng một pipeline cần truyền cùng lúc:

- `sku`: mã hàng;
- `amountCents`: tổng tiền dòng hàng đã tính;
- `level`: mức ưu tiên của dòng hàng.

Ba giá trị có **cùng một ý nghĩa nghiệp vụ tạm thời** và cần đi qua nhiều bước `map`, `sorted`, `filter`. Thay vì đưa chúng vào `Object[]` hoặc `Map<String, Object>` rồi ép kiểu thủ công, ta đặt tên rõ:

~~~java
record LineSummary(String sku, long amountCents, String level) {}

LineSummary row = new LineSummary("BOOK", 25_000, "HIGH");
System.out.println(row.amountCents()); // 25000
~~~

**Đoạn minh họa này phải được đặt trong một block/phương thức phù hợp** nếu muốn `LineSummary` là local record; đây chưa phải chương trình độc lập.

Tên các components vừa là hợp đồng kiểu vừa là tài liệu tại chỗ. `row.amountCents()` ít mơ hồ hơn `values[1]`; compiler kiểm tra kiểu `long` thay vì phải ép từ `Object`.

### 2.2. Kết hợp nhiều bước xử lý Stream

Trong một pipeline:

~~~java
record Classified(String code, long amountCents, boolean high) {}

var result = sales.stream()
        .map(sale -> {
            long total = Math.multiplyExact(sale.quantity(), sale.unitCents());
            return new Classified(
                    sale.code(), total, total >= thresholdCents);
        })
        .filter(Classified::high)
        .toList();
~~~

Đây là **đoạn minh họa, không biên dịch độc lập**: `sales`, `thresholdCents` và accessor của các phần tử `sales` phải được định nghĩa trong phương thức thật.

Local record đóng vai trò **kiểu trung gian có tên**, để kết quả của một bước được dùng ở các bước sau mà không tính lại `total`. `Stream.toList()` là API chuẩn từ Java 16, dùng được trong ví dụ Java 17 ở phần 7; danh sách kết quả của `toList()` là **unmodifiable**.

**Không phải cứ dùng Stream là cần local record.** Với pipeline chỉ chuyển `int` thành `String` và không cần ghép nhiều giá trị, một lệnh `map` trực tiếp dễ đọc hơn.

### 2.3. Khóa ghép cho `Map` hoặc `groupingBy`

Đôi khi một nhóm được xác định bởi **hai hoặc nhiều khóa đồng thời**: chẳng hạn kho hàng và mã sản phẩm. Nếu ghép chuỗi `warehouse + "|" + sku` để làm khóa, bạn phải xử lý dấu phân cách, escape và các trường hợp trùng lặp.

Local record cho phép biểu diễn chính xác cấu trúc khóa:

~~~java
record GroupKey(String warehouse, String sku) {}

Map<GroupKey, Integer> unitsByKey = new HashMap<>();
GroupKey key = new GroupKey("N", "BOOK");
unitsByKey.merge(key, 2, Integer::sum);
unitsByKey.merge(new GroupKey("N", "BOOK"), 1, Integer::sum);
System.out.println(unitsByKey.get(key)); // 3
~~~

Đoạn này **cần các import `java.util.Map` và `java.util.HashMap`**, và phải nằm trong cùng một block sau khai báo local record.

Hai đối tượng `new GroupKey("N", "BOOK")` có **cùng kiểu record và cùng các component values**, nên `equals`/`hashCode` mặc định giúp `Map` gộp về một khóa. Đây là một trường hợp sử dụng thực tế rất hữu ích.

**Lưu ý:** Nếu component của khóa là `String` hoặc kiểu bất biến phù hợp, khả năng duy trì tính ổn định của khóa cao. Nếu component chứa mảng hoặc object mutable, `equals`/`hashCode` mặc định **không bảo đảm ngữ nghĩa so sánh sâu và bất biến**; nên thiết kế lại khóa trước khi dùng làm `Map` key.

## 3. Cú pháp, phạm vi và quy tắc `static`

### 3.1. Local record phải được khai báo trong block

~~~java
class Processor {
    void process() {
        record Row(String id, int count) {}
        Row row = new Row("A", 2);
        System.out.println(row.id());
    }

    void anotherMethod() {
        // Row row = ...; // LỖI: tên Row ở process() không nằm trong phạm vi này.
    }
}
~~~

**Đoạn minh họa** này cho thấy tên local record không được đưa ra ngoài khối chứa khai báo. Local record có thể nằm trong block của phương thức, constructor hoặc các block hợp lệ khác; bài này dùng phương thức vì cần dữ liệu trung gian.

Không thêm modifier truy cập như `public`, `private`, `protected` hoặc từ khóa `static` trực tiếp vào **khai báo local record**:

~~~java
// KHÔNG HỢP LỆ khi viết trong thân phương thức:
public record Row(int value) {}  // local declaration không dùng public
static record Key(String id) {}  // local declaration không được viết static
~~~

Dù không ghi từ khóa `static`, **local record luôn ngầm định `static`** theo đặc tả Java. Đây là khác biệt quan trọng với **local normal class** thông thường.

### 3.2. “Ngầm định static” không cho record bắt biến cục bộ bên ngoài

Ví dụ sau **không biên dịch**:

~~~java
// Mã minh họa lỗi, đặt trong một phương thức.
long threshold = 20_000;

record Total(long cents) {
    boolean isHigh() {
        return cents >= threshold; // LỖI: record không capture biến threshold.
    }
}
~~~

Lý do: local record **ngầm định `static`**. Thân record không có enclosing instance và không được dùng trực tiếp biến/đối số của phương thức hay field instance của lớp bên ngoài như một local inner class.

**Cách đúng: tính giá trị bên ngoài record, rồi truyền vào constructor**:

~~~java
// Đoạn minh họa trong phương thức.
long threshold = 20_000;

record Total(long cents, boolean high) {}

long cents = 25_000;
Total total = new Total(cents, cents >= threshold);
System.out.println(total.high()); // true
~~~

Hoặc, nếu quan hệ với ngưỡng thật sự là một phần dữ liệu cần giữ, đưa ngưỡng vào record như một component:

~~~java
record Total(long cents, long threshold) {
    boolean high() {
        return cents >= threshold;
    }
}
~~~

Ở hai cách này, thân record chỉ truy cập **component của chính nó**. Trong một biểu thức `stream.map(...)` bao quanh lời gọi `new Total(...)`, **lambda** có thể dùng biến `threshold` của phương thức nếu biến đó *final hoặc effectively final*; khả năng capture của lambda **không truyền sang thân local record**.

### 3.3. Không bắt tham số kiểu của phương thức generic

Local record ngầm định `static` nên không trực tiếp dùng type parameter khai báo ở phương thức bao ngoài như component type:

~~~java
// Minh họa lỗi: T thuộc phương thức generic bao ngoài.
// static <T> void process(T value) {
//     record Box(T data) {} // Không hợp lệ: T ở ngữ cảnh static.
// }
~~~

Khi cần, định nghĩa type parameter **riêng cho record**:

~~~java
// Đoạn minh họa đặt trong phương thức generic.
record Box<U>(U data) {}
// Box<T> box = new Box<>(value);
~~~

Dòng sử dụng `Box<T>` trong comment chỉ có nghĩa khi `T` và `value` tồn tại trong phương thức generic. Đây là tính năng generic bình thường của record, không phải thủ thuật để “capture” kiểu của phương thức.

### 3.4. Local record vẫn có thể có constructor và phương thức

Giống record ở cấp lớp, local record có thể dùng **compact canonical constructor** để kiểm tra và chuẩn hóa thành phần:

~~~java
// Đoạn minh họa trong phương thức.
record Amount(long cents) {
    Amount {
        if (cents < 0) {
            throw new IllegalArgumentException("Amount must be nonnegative");
        }
    }

    long doubled() {
        return Math.multiplyExact(cents, 2);
    }
}
~~~

Khi dùng compact constructor, sau khi body kết thúc bình thường Java tự gán các tham số (có thể đã được chuẩn hóa) vào component fields. Không tự viết `this.cents = cents` trong compact constructor.

Record còn có thể chứa static methods/fields theo các quy tắc của record nói chung. Tuy nhiên, nếu logic của local record phình to thành nhiều nhiệm vụ, hãy xem xét tách loại dữ liệu đó thành member record hoặc một kiểu riêng.

## 4. Chọn local record hay kiểu khác?

| Tình huống | Nên cân nhắc | Lý do |
|---|---|---|
| Một phương thức cần bộ ba dữ liệu tạm để lọc/sắp xếp | **Local record** | Đặt tên các trường đúng nơi dùng, type-safe. |
| Một phương thức cần khóa ghép cho `Map` | **Local record** | `equals` và `hashCode` theo components, không phải tự ghép chuỗi. |
| Nhiều phương thức dùng lại cùng cấu trúc | **Member record** (ví dụ `private record` trong lớp) hoặc kiểu riêng | Các phương thức đều cần truy cập tên kiểu, tránh định nghĩa riêng lẻ. |
| Kiểu được trả về công khai trong API | Record có phạm vi truy cập phù hợp, DTO/domain type | Không thể đưa tên local record vào chữ ký API nằm ngoài block. |
| Chỉ cần một số nguyên hoặc một chuỗi trung gian | Biến cục bộ đơn giản | Không tạo kiểu mới chỉ để bọc một giá trị không cần thiết. |
| Đối tượng có vòng đời phức tạp, cập nhật trạng thái, danh tính thay đổi | Lớp thường/đối tượng nghiệp vụ phù hợp | Record mô tả giá trị dữ liệu; components của record là final. |
| Cần capture trực tiếp biến cục bộ từ method trong thân kiểu | Cân nhắc lambda hoặc local normal class | Local record ngầm định static, không capture enclosing state. |
| Dữ liệu được nhiều tầng hệ thống trao đổi | Kiểu domain/API dùng chung | Tránh làm nội bộ hóa một hợp đồng thực sự được tái sử dụng. |

**Nguyên tắc lựa chọn:** Local record phù hợp khi **dữ liệu có cấu trúc rõ ràng nhưng cấu trúc ấy chỉ thuộc một phép tính cục bộ**. Đừng biến local record thành một kiểu trao đổi ngầm cho toàn bộ ứng dụng.

## 5. Ví dụ ứng dụng: làm giàu dòng bán hàng trong Stream

Giả sử dữ liệu đầu vào là các dòng bán hàng gồm mã sản phẩm, số lượng và đơn giá theo **đơn vị nhỏ nhất của tiền** (`unitCents`); phương thức cần:

1. Tính tổng tiền từng dòng.
2. Đánh dấu `HIGH` nếu dòng có tổng tiền từ ngưỡng do caller cung cấp.
3. Sắp xếp giảm dần theo tổng tiền, nếu bằng nhau thì theo mã sản phẩm.
4. Xuất các dòng văn bản phục vụ màn hình/báo cáo.

**Dữ liệu trung gian** gồm `sku`, `amountCents`, `level`. Nó chỉ hữu ích trong phương thức xử lý, nên đặt:

~~~java
record LineSummary(String sku, long amountCents, String level) {}
~~~

**ngay trong phương thức** `classify(...)`. Phần Stream sau đó sử dụng `LineSummary::amountCents` và `LineSummary::sku` để sắp xếp mà không cần sử dụng mảng `Object[]` hay ép kiểu.

Tại bước:

~~~java
.map(s -> {
    long amount = Math.multiplyExact(s.units(), s.unitCents());
    String level = amount >= highThresholdCents ? "HIGH" : "NORMAL";
    return new LineSummary(s.sku(), amount, level);
})
~~~

Đây là **đoạn trích của phương thức đầy đủ ở phần 7**, không chạy độc lập.

- Lambda truy cập `highThresholdCents` (tham số phương thức và không bị gán lại, nên effectively final).
- Đối tượng `LineSummary` chỉ lưu ba **components** được truyền tường minh; thân local record không capture `highThresholdCents`.
- `Math.multiplyExact` tránh việc số tiền vượt miền `long` bị tràn số âm thầm: nếu tràn, nó ném `ArithmeticException`.
- Mốc `HIGH` và `NORMAL` là **quy tắc minh họa**; hệ thống thật có thể dùng một `enum` hoặc kiểu domain giàu nghĩa hơn.

**Tác động hiệu năng:** Mỗi `new LineSummary(...)` vẫn tạo một giá trị đối tượng về mặt ngữ nghĩa; đừng giả định local record được JVM lưu trên stack hoặc nhanh hơn tự động so với lớp thường. Trong pipeline lớn, đo bằng benchmark thực tế khi hiệu năng là yêu cầu; sự dễ đọc và rõ hợp đồng thường là lợi ích đầu tiên.

## 6. Ví dụ ứng dụng: dùng local record làm khóa ghép

Giả sử danh sách xuất kho có các dòng `warehouse`, `sku`, `units`; cần tổng hợp số lượng theo **cặp** kho và sản phẩm.

Tại phương thức tổng hợp:

~~~java
record GroupKey(String warehouse, String sku) {}
Map<GroupKey, Integer> totalUnits = new HashMap<>();
~~~

Ta có thể dùng:

~~~java
for (WarehouseSale sale : sales) {
    GroupKey key = new GroupKey(sale.warehouse(), sale.sku());
    totalUnits.merge(key, sale.units(), Math::addExact);
}
~~~

Đây là **đoạn trích** của chương trình đầy đủ ở phần 7; `WarehouseSale` và `sales` được khai báo ở đó.

Ví dụ:

- Lần thứ nhất: khóa `("N", "BOOK")` có `2` đơn vị.
- Lần thứ hai: khóa cùng giá trị có thêm `1` đơn vị.
- `Map.merge` gọi phép cộng để có `3` đơn vị cho khóa ghép đó.

Vì local record có `equals` và `hashCode` dựa trên components, hai khóa được khởi tạo khác thời điểm vẫn được nhận diện là **cùng khóa theo giá trị**. `Math::addExact` báo tràn số thay vì cộng sai nếu `int` vượt giới hạn.

**Tính xác định của kết quả:** `HashMap` không đảm bảo thứ tự duyệt. Khi cần đầu ra cố định, hãy `sorted(...)` theo kho rồi mã hàng như chương trình phần 7.

## 7. Chương trình Java 17 hoàn chỉnh

Lưu thành tệp **`LocalRecordIntermediateDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class LocalRecordIntermediateDemo {
    record Sale(String sku, int units, long unitCents) {
        Sale {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank() || units <= 0 || unitCents < 0) {
                throw new IllegalArgumentException("Invalid sale");
            }
        }
    }

    record WarehouseSale(String warehouse, String sku, int units) {}

    static List<String> classify(List<Sale> sales, long highThresholdCents) {
        if (highThresholdCents < 0) {
            throw new IllegalArgumentException("Invalid threshold");
        }

        // Local record: chỉ cần trong phương thức classify.
        record LineSummary(String sku, long amountCents, String level) {
            LineSummary {
                Objects.requireNonNull(sku, "sku");
                Objects.requireNonNull(level, "level");
                if (amountCents < 0) {
                    throw new IllegalArgumentException("Negative amount");
                }
            }
        }

        return sales.stream()
                .map(s -> {
                    long amount = Math.multiplyExact(s.units(), s.unitCents());
                    String level = amount >= highThresholdCents ? "HIGH" : "NORMAL";
                    return new LineSummary(s.sku(), amount, level);
                })
                .sorted(Comparator.comparingLong(LineSummary::amountCents)
                        .reversed().thenComparing(LineSummary::sku))
                .map(r -> r.sku() + " | " + r.amountCents() + " | " + r.level())
                .toList();
    }

    static List<String> groupByWarehouse(List<WarehouseSale> sales) {
        // Local record: khóa ghép chỉ cần trong phương thức tổng hợp này.
        record GroupKey(String warehouse, String sku) {}

        Map<GroupKey, Integer> totalUnits = new HashMap<>();
        for (WarehouseSale sale : sales) {
            GroupKey key = new GroupKey(sale.warehouse(), sale.sku());
            totalUnits.merge(key, sale.units(), Math::addExact);
        }

        return totalUnits.entrySet().stream()
                .sorted(Comparator
                        .comparing((Map.Entry<GroupKey, Integer> e) ->
                                e.getKey().warehouse())
                        .thenComparing(e -> e.getKey().sku()))
                .map(e -> e.getKey().warehouse() + "/" + e.getKey().sku()
                        + "=" + e.getValue())
                .toList();
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("BOOK", 2, 12_500),
                new Sale("PEN", 3, 2_000),
                new Sale("NOTE", 1, 7_500));

        classify(sales, 20_000).forEach(System.out::println);
        System.out.println("-- grouped --");

        List<WarehouseSale> warehouseSales = List.of(
                new WarehouseSale("N", "BOOK", 2),
                new WarehouseSale("S", "PEN", 3),
                new WarehouseSale("N", "BOOK", 1));
        groupByWarehouse(warehouseSales).forEach(System.out::println);
    }
}
~~~

Chạy bằng **JDK 17 trở lên**:

~~~bash
javac --release 17 -encoding UTF-8 LocalRecordIntermediateDemo.java
java LocalRecordIntermediateDemo
~~~

Đầu ra đã kiểm tra bằng `javac --release 17` và `java`:

~~~text
BOOK | 25000 | HIGH
NOTE | 7500 | NORMAL
PEN | 6000 | NORMAL
-- grouped --
N/BOOK=3
S/PEN=3
~~~

**Giải thích kết quả:**

1. `BOOK`: `2 × 12500 = 25000` cents, vượt ngưỡng `20000` nên `HIGH`.
2. `NOTE`: `1 × 7500 = 7500` cents, `NORMAL`.
3. `PEN`: `3 × 2000 = 6000` cents, `NORMAL`.
4. Sau khi `sorted(...)`, ba dòng được xếp theo `amountCents` giảm dần.
5. Hai dòng `WarehouseSale("N", "BOOK", ...)` được `GroupKey` gộp theo **cùng cặp** `("N", "BOOK")` thành `3`.
6. Bước sắp xếp `entrySet().stream().sorted(...)` làm thứ tự xuất kết quả không phụ thuộc vào thứ tự nội bộ của `HashMap`.

**Chọn nơi khai báo:** `Sale` và `WarehouseSale` là các **member records** của `LocalRecordIntermediateDemo` vì hai phương thức khác nhau/đầu vào cần gọi được tên kiểu ở cấp lớp. `LineSummary` và `GroupKey` là **local records** vì chỉ nội bộ của từng phép tính cần tên chúng. Đây là ranh giới tổ chức dữ liệu mà bài học muốn thể hiện.

**Giới hạn của ví dụ:** `WarehouseSale` không thêm validation để giữ phần minh họa tập trung vào local records; code thực tế nên kiểm tra các components của dữ liệu đầu vào theo hợp đồng hệ thống. Đơn vị `cents` chỉ là ví dụ dùng số nguyên để tránh nhiễu bởi phép tính dấu chấm động; miền tiền tệ thực tế có thể có quy tắc số chữ số thập phân và giới hạn khác.

## 8. Các quy tắc của record vẫn áp dụng ở phạm vi cục bộ

### 8.1. Component fields là final nhưng không phải bất biến sâu

~~~java
// Đoạn minh họa trong một phương thức.
record Row(String id, List<String> tags) {}
~~~

Record có trường `tags` kiểu `private final List<String>`, nhưng nếu caller giữ một `ArrayList`, việc sửa list gốc vẫn có thể thay đổi dữ liệu nhìn thấy qua `row.tags()`.

Nếu cần bảo vệ dữ liệu trung gian không bị sửa ngoài ý muốn:

~~~java
record Row(String id, List<String> tags) {
    Row {
        Objects.requireNonNull(id, "id");
        tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
    }
}
~~~

Đây là **đoạn minh họa trong phương thức**, cần các import `java.util.List` và `java.util.Objects` như ví dụ chính.

`List.copyOf` tạo một bản list unmodifiable; nó không clone sâu mọi phần tử. Với `String`, các phần tử là bất biến nên đây thường là giải pháp tốt. Nếu components giữ object mutable, cân nhắc thiết kế data carrier khác hoặc tạo bản sao phù hợp.

### 8.2. Record hỗ trợ equals/hashCode theo giá trị components

~~~java
// Đoạn minh họa đặt trong một block.
record Key(String region, String sku) {}

boolean same = new Key("N", "BOOK")
        .equals(new Key("N", "BOOK")); // true
~~~

Điều này phù hợp với `Map`/`Set` và phân nhóm. Nhưng nếu components là mảng, `equals` của mảng dùng so sánh tham chiếu thay vì nội dung; không nên trông đợi một local record chứa mảng tự tạo ngữ nghĩa giá trị sâu.

### 8.3. Accessor có tên giống component và không có tiền tố get

Với `record GroupKey(String warehouse, String sku) {}`, các phương thức là `warehouse()` và `sku()`. Đừng viết `getWarehouse()` trừ khi bạn tự thêm phương thức đó và có lý do. Các cú pháp như `GroupKey::sku` trong `Comparator` chính là method references tới accessor của record.

### 8.4. Local record không tự có hiệu suất đặc biệt

Một local record vẫn là lớp được biên dịch, có object được tạo bằng `new`. JVM có thể tối ưu theo ngữ cảnh, nhưng không có đảm bảo chung rằng local record “không cấp phát” hay “luôn ở stack”. Nếu dữ liệu trung gian quá lớn hoặc pipeline ảnh hưởng hiệu năng, đo bằng công cụ thích hợp trước khi kết luận.

## 9. Các lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai hoặc khó bảo trì | Cách sửa |
|---|---|---|
| Cho rằng local record có thể đọc `threshold` của phương thức trong instance method của record | Local record ngầm định static, không capture biến bao ngoài | Tính ở lambda/phương thức bao ngoài rồi truyền kết quả vào component |
| Viết `static record Key(...) {}` trong phương thức | Modifier `static` tường minh không hợp lệ ở local declaration | Viết `record Key(...) {}`; nó đã ngầm định static |
| Đưa `private record Temp(...) {}` vào phương thức | Local declaration không nhận modifier truy cập | Bỏ modifier hoặc chuyển thành member record nếu cần `private` |
| Trả một kiểu local record trong chữ ký phương thức | Tên kiểu không ở trong phạm vi của chữ ký | Trả DTO/interface công khai phù hợp hoặc chuyển kiểu lên cấp member |
| Sử dụng `Object[]` và ép kiểu số/chữ qua index | Thiếu tên và khả năng kiểm tra kiểu tại compile time | Dùng local record với components có tên và kiểu rõ |
| Trả về `List<Object>` chứa các local records không mô tả hợp đồng | Consumer ngoài method không gọi được tên loại cụ thể | Chuyển đổi thành loại kết quả có phạm vi phù hợp trước khi return |
| Dùng local record chứa `List` mutable mà không bảo vệ | Tham chiếu component final nhưng đối tượng list vẫn sửa được | Defensive copy khi tạo; cân nhắc bảo vệ phần tử mutable |
| Dùng local record chung cho nhiều phương thức qua định nghĩa trùng lặp | Logic/naming trùng, khó đồng bộ | Đưa ra member record hoặc kiểu riêng nếu tái sử dụng thực sự |
| Dùng local record chỉ cho một phép cộng đơn giản | Tăng cấu trúc vô ích | Dùng một biến cục bộ rõ nghĩa |
| Cho rằng `HashMap` sẽ xuất nhóm theo thứ tự chèn | `HashMap` không đảm bảo thứ tự | Sắp xếp kết quả nếu thứ tự là yêu cầu |
| Ngộ nhận local record là tính năng preview hiện nay vì từng được giới thiệu thời Java 14 | Records đã chuẩn hóa từ Java 16 | Trên Java 17+, dùng bình thường, không cần `--enable-preview` |

## 10. Quy trình áp dụng vào mã dự án

1. **Xác định dữ liệu trung gian thực sự có nhiều thành phần liên quan.** Ví dụ tổng tiền đã tính + mã sản phẩm + nhóm ưu tiên.
2. **Kiểm tra phạm vi sử dụng:** chỉ một block/phương thức thì bắt đầu bằng local record; nếu nhiều nơi cùng cần kiểu đó, chuyển sang member/domain record.
3. **Đặt tên có ý nghĩa:** `LineSummary`, `GroupKey`, `RiskResult` thay vì `Tmp` hoặc `Data`.
4. **Chỉ lưu các component cần thiết**; tránh nhân đôi thông tin có thể suy ra dễ dàng mà lại tạo nguy cơ bất nhất.
5. **Đảm bảo record không đọc enclosing locals trong thân nó**; mọi dữ liệu cần thiết phải truyền tường minh qua constructor.
6. **Thêm validation cho các invariant** nếu đầu vào có thể không hợp lệ; với components mutable, cân nhắc defensive copy.
7. **Trả về một kiểu hợp đồng rõ ràng** từ phương thức; chuyển local record thành kết quả public thích hợp hoặc dùng nó hoàn toàn trong phương thức.
8. **Kiểm tra đầu ra và đặc biệt là khóa `Map`/`Set`**, trường hợp giá trị trùng, null, tràn số và thứ tự sắp xếp nếu có.
9. **Chỉ tối ưu sau khi đo** nếu số lượng bản ghi trung gian lớn; đừng đánh đổi khả năng hiểu mã dựa trên phỏng đoán về hiệu năng.

## 11. Tự kiểm tra

**Câu 1.** Một phương thức nhận `List<OrderLine>`, tính tổng tiền và mức chiết khấu của từng dòng, sau đó sắp xếp theo tổng tiền. Ba giá trị chỉ cần trong phương thức này. Nên khai báo kiểu trung gian ở đâu?

**Đáp án:** Local record ngay trong phương thức, chẳng hạn `record ComputedLine(String sku, long totalCents, int discountPercent) {}`, nếu nó giúp các bước xử lý giữ nhiều thông tin có tên và kiểu rõ ràng.

**Câu 2.** Vì sao đoạn dưới không hợp lệ?

~~~java
// Mã minh họa bên trong phương thức.
int minimum = 10;
record Score(int value) {
    boolean passed() {
        return value >= minimum;
    }
}
~~~

**Đáp án:** Local record ngầm định static; thân nó không thể capture biến `minimum` của phương thức bao ngoài. Có thể truyền boolean `passed` được tính trước hoặc đưa `minimum` vào components nếu thật sự cần lưu ngưỡng.

**Câu 3.** `new Key("N", "BOOK")` và `new Key("N", "BOOK")` có gộp thành một khóa trong `HashMap<Key, ...>` không, nếu `Key` là `record Key(String warehouse, String sku) {}`?

**Đáp án:** Có, vì `equals`/`hashCode` mặc định sử dụng giá trị các components; hai chuỗi có nội dung tương đương.

**Câu 4.** Local record khai báo trong một phương thức có bảo đảm mọi instance sẽ hết sống ngay khi phương thức trả về không?

**Đáp án:** Không. Phạm vi **tên kiểu** và vòng đời **object** khác nhau. Object có thể còn được tham chiếu qua một kiểu mà nơi gọi nhìn thấy, nhưng khi cần API ổn định, nên định nghĩa kiểu kết quả bên ngoài phương thức.

**Câu 5.** Một local record gồm hai components là `String sku` và `List<Item> items`. Có thể khẳng định object hoàn toàn bất biến ngay sau `new` không?

**Đáp án:** Không. Trường `items` là final nhưng danh sách và các `Item` bên trong có thể mutable. Cần xem xét copy cấu trúc, bảo vệ accessor và phần tử mutable theo yêu cầu.

**Câu 6.** Java 17 có cần `--enable-preview` khi khai báo local record không?

**Đáp án:** Không. Records là tính năng chuẩn từ Java 16, nên `javac --release 17` biên dịch được cú pháp này.

## Tài liệu tham khảo

- [Oracle Java 17 — Record Classes, mục Local Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): ví dụ record cục bộ trong phương thức dùng dữ liệu tổng hợp; giới hạn implicitly static và các thành phần sinh tự động.
- [Java Language Specification SE 17 — `14.3 Local Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3): phạm vi và các modifier hợp lệ của local record.
- [JLS SE 17 — `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): cấu trúc, component fields, constructors và quy tắc record.
- [JLS SE 17 — `6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): phạm vi tên kiểu khai báo cục bộ.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): mốc chuẩn hóa records tại Java 16.
- [Java SE 17 — `Stream.toList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): thu thập kết quả thành unmodifiable list.
- [Java SE 17 — `Map.merge()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction)): cộng dồn giá trị theo khóa ghép.

**Ghi nhớ:** Local record là **kiểu dữ liệu có tên, có kiểm tra kiểu, chỉ khai báo trong phạm vi cần dùng**. Nó đặc biệt hữu ích khi một phương thức tạo bộ dữ liệu trung gian nhiều thành phần hoặc cần khóa ghép theo giá trị. Vì local record **ngầm định static**, hãy truyền dữ liệu vào components, không cho thân record phụ thuộc biến cục bộ bên ngoài.