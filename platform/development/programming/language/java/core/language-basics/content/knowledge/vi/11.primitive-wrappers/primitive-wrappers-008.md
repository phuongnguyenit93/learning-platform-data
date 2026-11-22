# Chọn kiểu nguyên thủy hay lớp bao theo yêu cầu dữ liệu — Java 17+

## 1. Nguyên tắc quyết định

Java cung cấp hai dạng liên quan nhưng **không tương đương**:

- **Kiểu nguyên thủy** (*primitive*), ví dụ `int`, `boolean`, `double`: giữ trực tiếp một giá trị thuộc miền của kiểu; **không thể nhận `null`**.
- **Lớp bao nguyên thủy** (*wrapper class*), ví dụ `Integer`, `Boolean`, `Double`: biến giữ **tham chiếu tới đối tượng wrapper** (hoặc `null`), có thể dùng trong generic, collection và những API yêu cầu object.

~~~java
int stock = 0;               // Có dữ liệu: số lượng thật sự bằng 0
Integer reportedStock = null; // Chưa có dữ liệu, chưa phải số 0

boolean enabled = false;     // Có dữ liệu: trạng thái không bật
Boolean approved = null;     // Chưa được duyệt, chưa phải false
~~~

**Câu hỏi quyết định đầu tiên không phải “kiểu nào tốt hơn?” mà là “dữ liệu có được phép vắng mặt hay không?”**

Nếu giá trị **luôn phải tồn tại** và chủ yếu dùng trong tính toán/điều kiện, primitive thường phù hợp. Nếu cần **biểu diễn trạng thái vắng mặt** hoặc API yêu cầu kiểu tham chiếu, wrapper có thể cần thiết. Dù chọn wrapper, vẫn phải quy định rõ cách xử lý `null`.

## 2. Bảng tám cặp primitive và wrapper

| Primitive | Wrapper | Đặc điểm dữ liệu điển hình |
|---|---|---|
| `byte` | `Byte` | Số nguyên 8 bit có dấu |
| `short` | `Short` | Số nguyên 16 bit có dấu |
| `int` | `Integer` | Số đếm/số nguyên 32 bit |
| `long` | `Long` | Số nguyên 64 bit |
| `float` | `Float` | Số dấu phẩy động 32 bit |
| `double` | `Double` | Số dấu phẩy động 64 bit |
| `char` | `Character` | Một UTF-16 code unit |
| `boolean` | `Boolean` | Giá trị true hoặc false |

`String` không phải kiểu nguyên thủy và cũng không phải lớp bao của `char`; nó là class biểu diễn một chuỗi UTF-16 code units. `Void` có vai trò đặc biệt trong một số API phản chiếu/generic nhưng **không có giá trị primitive `void` để boxing như các cặp trên**.

Ví dụ chuyển đổi tự động (*autoboxing* và *unboxing*):

~~~java
int primitive = 12;
Integer boxed = primitive; // int -> Integer
int restored = boxed;      // Integer -> int

System.out.println(restored); // 12
~~~

Việc Java hỗ trợ chuyển đổi tự động **không xóa bỏ** khác biệt giữa primitive và wrapper, đặc biệt là trạng thái `null` và cách so sánh.

## 3. Bảng quyết định theo yêu cầu dữ liệu

| Yêu cầu | Thường ưu tiên | Lý do |
|---|---|---|
| Số lượng đơn hàng **bắt buộc có giá trị** | `int` | 0 là một số lượng hợp lệ; không có trạng thái null |
| ID nguyên bắt buộc, vượt giới hạn int | `long` | Miền nguyên 64 bit, không cần wrapper khi không có nullable |
| Số lượng **chưa được nhập hoặc chưa báo cáo** | `Integer` | Phân biệt null với số 0 |
| Cờ bật/tắt chỉ có hai trạng thái | `boolean` | Đúng hai trạng thái `true`, `false` |
| Trạng thái duyệt gồm có/chưa/không | `Boolean` hoặc `enum` | `null` có thể biểu thị chưa xác định; enum rõ hơn khi trạng thái có ý nghĩa nghiệp vụ |
| API nhận hoặc trả `List<Integer>` | `Integer` | Generic Java 17 cần reference type |
| Mảng phép đo lớn, tính toán lặp nhiều | `int[]`, `double[]` khi phù hợp | Tránh nhu cầu wrapper từng phần tử |
| Trả kết quả tìm kiếm số nguyên có thể không có | `OptionalInt` hoặc hợp đồng nullable rõ ràng | Tách “không tìm thấy” khỏi giá trị 0 |
| Trường dữ liệu nguồn bắt buộc nhưng chưa xác minh | Kiểm tra trước rồi primitive | Không biến “không biết” thành 0/false |
| Số tiền cần đúng chính xác thập phân | `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất | `Double` wrapper không sửa sai số binary floating-point |

**Điểm chốt:** tính **có mặt/vắng mặt**, **miền giá trị**, **độ chính xác** và **API sử dụng** quan trọng hơn sở thích viết kiểu. Một kiểu wrapper không phải luôn chậm/không an toàn, và primitive cũng không tự khiến dữ liệu hợp lệ về nghiệp vụ.

## 4. Phân biệt “không có dữ liệu” với số 0

Giả sử ứng dụng thống kê số đơn hàng đã được xác nhận:

- `confirmedOrders = 0`: hệ thống xác nhận **không có đơn hàng nào**.
- `confirmedOrders = null`: **chưa nhận được báo cáo**, chưa thể khẳng định bằng 0.

~~~java
Integer confirmedOrders = null;

if (confirmedOrders == null) {
    System.out.println("no report");
} else {
    System.out.println("confirmed=" + confirmedOrders);
}
~~~

Đầu ra:

~~~text
no report
~~~

Nếu ép dữ liệu thiếu thành 0 tùy tiện:

~~~java
int count = confirmedOrders == null ? 0 : confirmedOrders;
~~~

thì bạn **đã quyết định gộp** hai trạng thái khác nhau. Điều đó chỉ đúng nếu yêu cầu nghiệp vụ thật sự cho phép coi “chưa có báo cáo” là 0, ví dụ một phép hiển thị có nhãn “mặc định 0” và có giải thích.

**Quy tắc thiết kế API:** nếu giá trị bắt buộc, validate lúc nhận input hoặc lúc tạo object thay vì đưa một biến `Integer` tùy ý xuống sâu các tầng tính toán rồi hy vọng chúng không `null`.

## 5. Boolean và bài toán ba trạng thái

Một `boolean` có đúng hai giá trị `true`/`false`. Với `Boolean`, tham chiếu còn có thể `null`.

~~~java
Boolean approved = null;

if (approved == null) {
    System.out.println("pending");
} else if (approved) {
    System.out.println("approved");
} else {
    System.out.println("rejected");
}
~~~

Đầu ra:

~~~text
pending
~~~

Trường hợp này hợp lý khi dữ liệu có **ba trạng thái**: chưa đánh giá, đồng ý, từ chối. Tuy nhiên, nếu hệ thống có nhiều trạng thái hơn (đang duyệt, tạm hoãn, bị khóa...), dùng `enum` thường rõ nghĩa hơn:

~~~java
enum Decision {
    PENDING, APPROVED, REJECTED
}

Decision decision = Decision.PENDING;
~~~

**Đừng lạm dụng `null` làm một “trạng thái bí mật”** khi API không mô tả ý nghĩa của nó. Có thể dùng wrapper nullable, nhưng phải thống nhất hợp đồng dữ liệu và tài liệu hóa cách xử lý.

## 6. Giá trị mặc định của field khác với biến cục bộ

Nếu tạo object Java mà **không gán khởi tạo cho field**, primitive field nhận default value; reference field mặc định `null`:

~~~java
static final class Defaults {
    int count;            // 0
    Integer optionalCount; // null
    boolean enabled;      // false
    Boolean optionalEnabled; // null
}
~~~

Điều này hữu ích để hiểu hành vi, nhưng **không chứng minh các default value đó là dữ liệu hợp lệ**.

| Field | Mặc định khi tạo object | Nguy cơ hiểu sai |
|---|---|---|
| `int count` | `0` | 0 có thể bị nhầm với “chưa nạp dữ liệu” |
| `Integer count` | `null` | Unboxing khi chưa kiểm tra sẽ lỗi |
| `boolean enabled` | `false` | false có thể bị nhầm với “chưa đánh giá” |
| `Boolean enabled` | `null` | Phải quy định cách xử lý chưa xác định |

**Biến cục bộ không tự nhận default value:**

~~~java
static void example() {
    int count;
    // System.out.println(count); // Lỗi compile: biến cục bộ chưa gán
    count = 0;
    System.out.println(count); // 0
}
~~~

Hãy khởi tạo field có ý nghĩa rõ ràng hoặc dùng constructor để buộc cung cấp các giá trị bắt buộc.

## 7. Đưa yêu cầu dữ liệu vào model: record Java 17

Một `record` giúp thể hiện ranh giới **bắt buộc** và **có thể chưa có** trong chữ ký:

~~~java
record Stock(String sku, int onHand, Integer reserved, Boolean approved) {
    Stock {
        java.util.Objects.requireNonNull(sku, "sku is required");
        if (onHand < 0) {
            throw new IllegalArgumentException("negative onHand");
        }
        if (reserved != null && reserved < 0) {
            throw new IllegalArgumentException("negative reserved");
        }
    }
}
~~~

Ý nghĩa:

- `onHand` là `int`: bắt buộc có giá trị tại thời điểm tạo record, nhưng vẫn cần kiểm tra `onHand >= 0`.
- `reserved` là `Integer`: có thể chưa nhận dữ liệu (null), có thể nhận giá trị **0** hoặc số dương.
- `approved` là `Boolean`: có thể chưa đánh giá, `true` hoặc `false`.
- `sku` là `String` tham chiếu: không tự cấm null, nên constructor gọi `Objects.requireNonNull`.

~~~java
Stock unknown = new Stock("SKU-1", 10, null, null);
Stock knownZero = new Stock("SKU-1", 10, 0, false);

System.out.println(unknown.reserved() == null); // true
System.out.println(knownZero.reserved());         // 0
~~~

**Điểm cốt lõi:** Java không có kiểu primitive nullable. Nếu phải đại diện vắng mặt, cần một cơ chế trong model (wrapper, `OptionalInt` cho API trả về, trạng thái riêng, object kết quả...) và phải thực thi hợp đồng nghiệp vụ bằng validation.

## 8. Chặn null ở ranh giới dữ liệu

Một `Integer` hoặc `Boolean` có thể chứa `null`. Khi Java cần giá trị primitive để cộng, so sánh với số hoặc chạy `if (flag)`, unboxing `null` sẽ gây `NullPointerException`. Điểm cần quyết định trong thiết kế dữ liệu là **được phép thiếu** hay **phải từ chối đầu vào thiếu**.

~~~java
static int requireCount(Integer count) {
    if (count == null) {
        throw new IllegalArgumentException("count is required");
    }
    return count; // Chỉ unbox sau khi kiểm tra
}
~~~

Nếu null là trạng thái hợp lệ, giữ wrapper đến lúc có quy tắc xử lý rõ ràng; đừng mặc định đổi null thành 0. Bài unboxing null phân tích chi tiết các bẫy ba ngôi, short-circuit và điều kiện.

## 9. So sánh theo giá trị hay tham chiếu?

Khi hai biến có kiểu `Integer`, `a == b` hỏi chúng có cùng object không; cache có thể khiến hai wrapper của một số nhỏ dùng chung object. Khi muốn hỏi hai **giá trị** có bằng nhau, chọn `a.equals(b)` nếu `a` không null, hoặc `Objects.equals(a, b)` khi cả hai có thể null.

~~~java
Integer first = Integer.valueOf(1000);
Integer second = Integer.valueOf(1000);
System.out.println(java.util.Objects.equals(first, second)); // true
~~~

Với `Integer == int`, Java unbox để so số; nếu wrapper null sẽ gây NPE. `Integer.equals(Long)` không tự đổi kiểu để so. Các bài equality và cache là nơi giải thích chính cho những quy tắc này.

## 10. Generic collection và chính sách dữ liệu thiếu

`List<Integer>` chứa wrapper vì generic Java 17 dùng kiểu tham chiếu. Khi chuyển sang `int` để tính toán, mỗi phần tử phải có giá trị:

~~~java
java.util.List<Integer> readings =
        java.util.Arrays.asList(2, null, 3);
int sum = 0;
for (Integer n : readings) {
    if (n != null) {
        sum += n;
    }
}
System.out.println(sum); // 5
~~~

Bỏ qua null ở đây là **chính sách minh họa**, không phải mặc định đúng cho mọi hệ thống. `List.of(...)` không chấp nhận phần tử null. Nếu dữ liệu số luôn bắt buộc, cần tính toán nhiều và không phụ thuộc generic, mảng primitive hoặc primitive stream có thể hợp lý hơn; phần hiệu năng ở dưới giải thích cách đánh giá.

## 11. `OptionalInt` cho API trả về kết quả có thể vắng mặt

Đôi khi caller cần biết **một kết quả số nguyên có tồn tại không**, nhưng bạn không muốn trả `Integer` nullable. Java cung cấp `java.util.OptionalInt`:

~~~java
import java.util.OptionalInt;

static OptionalInt findScore(boolean found) {
    return found ? OptionalInt.of(0) : OptionalInt.empty();
}
~~~

Bên gọi:

~~~java
OptionalInt missing = findScore(false);
OptionalInt existingZero = findScore(true);

System.out.println(missing.isEmpty());     // true
System.out.println(existingZero.orElse(-1)); // 0
~~~

`OptionalInt.empty()` **khác** `OptionalInt.of(0)`. Một API dùng `OptionalInt` thể hiện trạng thái có/không ngay trên kiểu trả về.

**Cân nhắc thực tế:** `OptionalInt` phù hợp nhất ở **kiểu trả về của method** có thể không có kết quả. Không mặc định thay mọi field `Integer` bằng field `OptionalInt`, vì các framework/định dạng dữ liệu hoặc code hiện có có thể có quy ước riêng. Chọn dựa trên hợp đồng API và hệ sinh thái đang dùng.

## 12. Primitive và wrapper về hiệu năng, bộ nhớ

Wrapper là object tham chiếu và có thể phát sinh chi phí **boxing/unboxing**, lưu tham chiếu, cấp phát, áp lực garbage collection tùy tình huống.

~~~java
int[] primitiveArray = new int[1_000];
Integer[] wrapperArray = new Integer[1_000];
~~~

Hai cấu trúc **khác nhau về ý nghĩa**:

- `int[]` giữ 1000 giá trị `int`, mỗi phần tử mặc định 0.
- `Integer[]` giữ 1000 **tham chiếu**, mỗi phần tử ban đầu null. Tạo mảng **không** tự tạo 1000 object `Integer`.
- Cách bố trí bộ nhớ, header và căn chỉnh object phụ thuộc JVM; **không** suy ra tổng RAM thực tế chỉ từ `Integer.SIZE`.

Trong xử lý số liệu khối lượng lớn, primitive array, primitive streams (`IntStream`, `LongStream`, `DoubleStream`) có thể giúp tránh một số wrapper không cần thiết:

~~~java
int total = java.util.stream.IntStream.of(2, 3, 5).sum();
System.out.println(total); // 10
~~~

Nhưng **không** nên khẳng định mọi primitive luôn nhanh hơn mọi wrapper trong mọi JVM. JIT có thể tối ưu hóa, cache có thể tái sử dụng wrapper, và hiệu năng còn tùy workload. Khi tối ưu thật sự quan trọng, hãy đo benchmark có phương pháp (ví dụ JMH).

**Nguyên tắc:** ưu tiên mô hình dữ liệu đúng trước; nếu nhiều lựa chọn đều đúng, cân nhắc tính đơn giản và đo hiệu năng thực tế.

## 13. Wrapper không giải quyết bài toán độ chính xác thập phân

Chọn `Double` thay `double` chỉ thay đổi **cách đóng gói giá trị và khả năng null**, không thay đổi quy tắc biểu diễn **binary floating-point**:

~~~java
double primitive = 0.1 + 0.2;
Double boxed = primitive;

System.out.println(primitive); // 0.30000000000000004
System.out.println(boxed);     // 0.30000000000000004
~~~

Nếu nghiệp vụ yêu cầu phép tính số tiền chính xác theo thập phân, cần chọn mô hình như `BigDecimal` hoặc số nguyên biểu diễn đơn vị nhỏ nhất:

~~~java
java.math.BigDecimal exact =
        new java.math.BigDecimal("0.1")
                .add(new java.math.BigDecimal("0.2"));

System.out.println(exact); // 0.3
~~~

**Tách hai quyết định độc lập:**

1. Giá trị có thể **thiếu** không? → primitive hay wrapper/kiểu kết quả có trạng thái vắng mặt.
2. Giá trị cần **độ chính xác và miền nào**? → int/long/double/BigDecimal/... theo toán học và nghiệp vụ.

Dùng wrapper chỉ vì “có vẻ chính xác hơn primitive” là sai về bản chất.

## 14. Thiết kế API: nêu rõ hợp đồng null và validation

Ví dụ một method nhận số lượng được phép thiếu:

~~~java
static String describeCount(Integer count) {
    return count == null ? "not reported" : "count=" + count;
}
~~~

Nó hợp lý khi **thiếu là một trạng thái hợp lệ**. Ngược lại, nếu dữ liệu bắt buộc có số lượng, hãy khai báo primitive:

~~~java
static boolean hasStock(int count) {
    if (count < 0) {
        throw new IllegalArgumentException("negative stock");
    }
    return count > 0;
}
~~~

Một field wrapper không nhất thiết nên `null`, và một primitive mặc định không nhất thiết hợp lệ. **Thiết kế dữ liệu cần thống nhất với validation**.

Các API nhận dữ liệu ngoài (JSON, database, HTTP request, form...) còn có thể phân biệt **không gửi field**, **gửi null**, **gửi 0**, hoặc **gửi chuỗi "0"**. Mapping cụ thể phụ thuộc framework, schema và quy ước API; không được đoán rằng mọi framework Java đều tự chuyển chúng thành primitive/wrapper giống nhau.

Khi nhận wrapper từ lớp ngoài, validate/chuẩn hóa tại ranh giới trước khi chuyển sang logic nội bộ cần primitive.

## 15. Chương trình Java 17 độc lập: chọn kiểu theo yêu cầu thực tế

Tạo tệp đúng tên **`PrimitiveOrWrapperDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.OptionalInt;

public final class PrimitiveOrWrapperDemo {
    private PrimitiveOrWrapperDemo() {}

    static final class Defaults {
        int count;
        Integer optionalCount;
        boolean enabled;
        Boolean optionalEnabled;
    }

    record Stock(String sku, int onHand, Integer reserved, Boolean approved) {
        Stock {
            Objects.requireNonNull(sku, "sku is required");
            if (onHand < 0) {
                throw new IllegalArgumentException("negative onHand");
            }
            if (reserved != null && reserved < 0) {
                throw new IllegalArgumentException("negative reserved");
            }
        }
    }

    static String approvalLabel(Boolean approved) {
        if (approved == null) {
            return "unknown";
        }
        return approved ? "approved" : "rejected";
    }

    static int sumPresent(List<Integer> values) {
        int total = 0;
        for (Integer value : values) {
            if (value != null) {
                total += value;
            }
        }
        return total;
    }

    static OptionalInt findCount(boolean found) {
        return found ? OptionalInt.of(0) : OptionalInt.empty();
    }

    public static void main(String[] args) {
        Defaults defaults = new Defaults();
        System.out.println("default int=" + defaults.count);
        System.out.println("default Integer=" + defaults.optionalCount);
        System.out.println("default boolean=" + defaults.enabled);
        System.out.println("default Boolean=" + defaults.optionalEnabled);

        Stock unknown = new Stock("SKU-1", 10, null, null);
        Stock explicit = new Stock("SKU-1", 10, 0, false);
        System.out.println("required stock=" + unknown.onHand());
        System.out.println("missing reserved=" + (unknown.reserved() == null));
        System.out.println("reported reserved zero=" + explicit.reserved());
        System.out.println("approval unknown=" + approvalLabel(unknown.approved()));
        System.out.println("approval false=" + approvalLabel(explicit.approved()));
        System.out.println("approval true=" + approvalLabel(true));

        List<Integer> readings = Arrays.asList(2, null, 3);
        System.out.println("sum present=" + sumPresent(readings));

        Integer first = Integer.valueOf(1000);
        Integer second = Integer.valueOf(1000);
        Integer alias = first;
        System.out.println("wrapper value equality="
                + Objects.equals(first, second));
        System.out.println("same wrapper alias=" + (first == alias));

        Integer counter = 3;
        Integer snapshot = counter;
        counter++;
        System.out.println("wrapper counter=" + counter);
        System.out.println("wrapper snapshot=" + snapshot);

        Integer missing = null;
        try {
            int invalid = missing;
            System.out.println(invalid);
        } catch (NullPointerException ex) {
            System.out.println("null unboxing rejected");
        }

        OptionalInt absent = findCount(false);
        OptionalInt presentZero = findCount(true);
        System.out.println("optional absent=" + absent.isEmpty());
        System.out.println("optional zero=" + presentZero.orElse(-1));

        double binarySum = 0.1 + 0.2;
        Double wrappedSum = binarySum;
        System.out.println("double result=" + wrappedSum);
        System.out.println("decimal exact="
                + new BigDecimal("0.1").add(new BigDecimal("0.2")));

        try {
            new Stock("SKU-X", -1, null, null);
        } catch (IllegalArgumentException ex) {
            System.out.println("negative stock rejected");
        }
    }
}
~~~

**Yêu cầu:** JDK 17+; mở terminal trong thư mục chứa tệp. Không cần Maven, Gradle hoặc thư viện bên ngoài JDK.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 PrimitiveOrWrapperDemo.java
java -cp . PrimitiveOrWrapperDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\PrimitiveOrWrapperDemo.java
java -cp . PrimitiveOrWrapperDemo
~~~

**Expected output chính xác:**

~~~text
default int=0
default Integer=null
default boolean=false
default Boolean=null
required stock=10
missing reserved=true
reported reserved zero=0
approval unknown=unknown
approval false=rejected
approval true=approved
sum present=5
wrapper value equality=true
same wrapper alias=true
wrapper counter=4
wrapper snapshot=3
null unboxing rejected
optional absent=true
optional zero=0
double result=0.30000000000000004
decimal exact=0.3
negative stock rejected
~~~

**Điểm cần tự kiểm chứng:**

1. Field primitive `int`/`boolean` mặc định 0/false; field wrapper mặc định null.
2. Cùng một kiểu `Integer` phân biệt `reserved=null` và `reserved=0`.
3. `Boolean` cho phép trạng thái unknown bên cạnh false/true, nếu API có hợp đồng tương ứng.
4. Vòng lặp `List<Integer>` chủ động bỏ qua null **theo chính sách của ví dụ**.
5. So wrapper 1000 qua `Objects.equals` không dựa vào identity cache; `first == alias` true vì thật sự cùng tham chiếu.
6. Tăng `counter` không sửa object wrapper mà `snapshot` đang giữ.
7. Unboxing null được catch có chủ đích, minh họa lý do phải kiểm tra dữ liệu.
8. `OptionalInt.empty()` khác `OptionalInt.of(0)`.
9. `Double` wrapper không làm phép cộng thập phân trở nên exact; `BigDecimal` từ chuỗi đáp ứng một mô hình khác.
10. Constructor từ chối số lượng âm, thể hiện chọn đúng kiểu vẫn cần validation.

## 16. Những lỗi thường gặp và cách sửa

| Lỗi hoặc giả định | Vấn đề | Cách làm phù hợp |
|---|---|---|
| Dùng `int` cho dữ liệu “chưa được nhập” rồi ngầm dùng 0 | Gộp thiếu dữ liệu với số 0 | Dùng `Integer`/trạng thái vắng mặt rõ nghĩa |
| Dùng `Integer` cho mọi biến đếm | Tăng nhu cầu kiểm tra null/boxing | Dùng `int` khi dữ liệu bắt buộc và tính toán nhiều |
| `Boolean flag = null; if (flag)` | Unboxing null gây NPE | Kiểm tra null hoặc thiết kế enum |
| `Integer n = null; int x = n;` | Unboxing null gây NPE | Validate hoặc chọn policy rõ |
| Hai `Integer` so bằng `==` khi muốn so số | `==` so identity của hai tham chiếu | `equals`/`Objects.equals` |
| Coi mặc định field `int = 0` là dữ liệu hợp lệ | Default JVM không phải validation nghiệp vụ | Constructor/validation |
| Coi `Integer = null` tương đương số 0 | Mất ý nghĩa “chưa có dữ liệu” | Giữ và xử lý riêng null |
| Dùng `List<int>` | Generic Java 17 không nhận primitive | `List<Integer>` |
| Duyệt `List<Integer>` bằng `for (int n : list)` khi có null | Unboxing null trong vòng lặp | Validation hoặc xử lý từng `Integer` |
| Dùng `OptionalInt` bất kể API/framework | Khác hợp đồng/khả năng tích hợp | Dùng phù hợp ở kiểu trả về |
| Dùng `Double` thay `double` để sửa sai số thập phân | Wrapper không đổi biểu diễn binary | `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất |
| Cho rằng wrapper luôn cấp phát mới khi boxing | JVM có thể cache/tối ưu | Không phụ thuộc identity/cấp phát |
| Dùng primitive để tránh mọi lỗi dữ liệu | Primitive vẫn có giới hạn/tràn/giá trị không hợp lệ | Validation và chọn miền giá trị |
| Tự động đổi null → 0 ở mọi nơi | Có thể làm sai ý nghĩa nghiệp vụ | Thống nhất chính sách mặc định trước |

## 17. Bài tập ngắn và đáp án

### Bài A — số lượng đã báo cáo

`count=0` khác `count=null` như thế nào trong hệ thống ghi nhận hàng hóa?

**Đáp án:** `0` nghĩa là có một báo cáo xác nhận số lượng bằng không; `null` có thể biểu thị chưa có số liệu (nếu hợp đồng API định nghĩa như vậy). Nếu cần phân biệt hai trạng thái này, `Integer` hoặc kiểu có trạng thái vắng mặt là phù hợp.

### Bài B — primitive hay wrapper cho cờ trạng thái?

API chỉ có bật/tắt, không có trạng thái chưa biết. Chọn `boolean` hay `Boolean`?

**Đáp án:** thường chọn `boolean`. Nếu API có trạng thái “chưa duyệt” riêng, có thể dùng `Boolean` cùng quy tắc null hoặc một `enum` mang tên trạng thái rõ ràng.

### Bài C — null và unboxing

~~~java
Integer n = null;
// System.out.println(n + 1);
~~~

**Đáp án:** nếu bật dòng comment sẽ biên dịch được nhưng ném `NullPointerException` lúc chạy, vì phép cộng phải unbox `n` thành int trước.

### Bài D — so giá trị

~~~java
Integer a = Integer.valueOf(1000);
Integer b = Integer.valueOf(1000);
System.out.println(java.util.Objects.equals(a, b));
~~~

**Đáp án:** `true`. Dùng equality theo giá trị, không phụ thuộc vùng object cache.

### Bài E — generic

~~~java
java.util.List<Integer> nums = java.util.List.of(2, 3);
int sum = 0;
for (int n : nums) {
    sum += n;
}
System.out.println(sum);
~~~

**Đáp án:** `5`. List dùng wrapper; mỗi phần tử được unbox khi gán vào biến vòng lặp int. Đối với `List.of`, không được đưa null vào danh sách.

### Bài F — lựa chọn kiểu và miền nghiệp vụ

Một field `age` luôn phải được cung cấp và phải không âm. Dùng `int` có đủ để đảm bảo dữ liệu hợp lệ?

**Đáp án:** **chưa đủ**. `int` loại bỏ khả năng null nhưng vẫn chứa số âm. Cần kiểm tra `age >= 0` tại ranh giới input hoặc constructor.

## 18. Checklist và kết luận

- [ ] Biết tám cặp primitive-wrapper Java.
- [ ] Hiểu primitive không mang `null`, wrapper có thể `null`.
- [ ] Phân biệt dữ liệu bằng 0/false với dữ liệu chưa có.
- [ ] Chọn primitive khi giá trị bắt buộc và chủ yếu tính toán.
- [ ] Chọn wrapper khi thật sự cần nullable hoặc dùng API/generic yêu cầu reference type.
- [ ] Biết default field primitive và wrapper khác nhau; local variable phải được gán trước khi đọc.
- [ ] Biết boxing/unboxing và xử lý null trước khi unbox.
- [ ] Không so giá trị của hai wrapper bằng `==`.
- [ ] Kiểm tra input/miền dữ liệu ngay cả khi chọn primitive.
- [ ] Hiểu `List<Integer>` khác `int[]`, và lưu ý null trong collection.
- [ ] Biết `OptionalInt` là một lựa chọn cho method trả kết quả có thể vắng mặt.
- [ ] Không nhầm `Double` wrapper với giải pháp tính toán decimal chính xác.
- [ ] Biết cân nhắc bộ nhớ/hiệu năng dựa trên workload, không chỉ cảm tính.
- [ ] Chạy `PrimitiveOrWrapperDemo.java` trên Java 17+ và so từng dòng expected output.

**Kết luận:** Chọn **primitive** hay **wrapper** dựa trước tiên vào **ý nghĩa dữ liệu**: bắt buộc hay có thể vắng mặt. Primitive phù hợp với giá trị luôn tồn tại và tính toán trực tiếp; wrapper phù hợp với nullable, collection và API cần object. Dù chọn kiểu nào, bạn vẫn cần quy định miền hợp lệ, cách xử lý null, phép so sánh và độ chính xác đúng với yêu cầu thực tế.