# Phân biệt tham chiếu null với giá trị số 0 trong Java

## 1. Vấn đề: “không có giá trị” khác “có giá trị bằng 0”

Trong Java, `null` và số `0` biểu thị hai trạng thái khác nhau:

- **`null`**: biến có kiểu tham chiếu hiện không trỏ tới đối tượng nào. Đây có thể là dữ liệu chưa được cung cấp, chưa biết, không áp dụng hoặc một lỗi trong việc khởi tạo, tùy hợp đồng của ứng dụng.
- **`0`**: một giá trị số thực sự, thường mang ý nghĩa đếm được bằng không, số dư bằng không, kết quả phép tính bằng không hoặc mã trạng thái có giá trị 0.

Với primitive `int`, không thể gán `null`. Với wrapper `Integer`, biến có thể tham chiếu một đối tượng chứa giá trị 0 **hoặc** chứa `null`.

~~~java
int primitiveZero = 0;
Integer boxedZero = Integer.valueOf(0);
Integer missing = null;

System.out.println(primitiveZero); // 0
System.out.println(boxedZero);     // 0
System.out.println(missing);       // null
~~~

Ba dòng trên là ví dụ đặt trong một phương thức. Khi in bằng `System.out.println(Object)`, tham chiếu null cho ra chữ `null`; điều đó không đồng nghĩa có một đối tượng `Integer` đặc biệt mang giá trị số “null”.

Mục tiêu của bài này là chọn đúng mô hình cho dữ liệu có thể thiếu, nhận diện mọi chỗ Java **tự unbox**, và không vô tình gộp “không biết số lượng” thành “số lượng chắc chắn bằng 0”.

## 2. Primitive và wrapper: hai miền giá trị khác nhau

| Kiểu | Giá trị số 0 | Có thể chứa null? | Dùng khi |
| --- | --- | --- | --- |
| `int` | `0` | Không | Luôn có số nguyên 32 bit hợp lệ |
| `long` | `0L` | Không | Luôn có số nguyên 64 bit hợp lệ |
| `double` | `0.0` | Không | Luôn có số thực, kể cả ±0.0 |
| `Integer` | `Integer.valueOf(0)` | Có | Cần phân biệt số 0 và thiếu số nguyên |
| `Long` | `Long.valueOf(0L)` | Có | Cần phân biệt số 0 và thiếu số nguyên dài |
| `Double` | `Double.valueOf(0.0)` | Có | Cần phân biệt số 0 và thiếu số thực |

`Integer`, `Long`, `Double`, `Short`, `Byte`, `Float` là các lớp wrapper cho primitive số tương ứng. `Character` và `Boolean` cũng là wrapper primitive, dù không phải lớp con của `Number`.

~~~java
// int n = null; // Không biên dịch: null không chuyển được thành int.
Integer n = null; // Hợp lệ: Integer là kiểu tham chiếu.
Integer z = 0;    // Hợp lệ: autoboxing từ int 0 thành Integer.
~~~

Một đối tượng wrapper bất biến: `Integer.valueOf(0)` đại diện giá trị 0, và không thể thay đổi nội dung của đối tượng thành 1. Tuy vậy, biến tham chiếu không `final` có thể được gán lại sang object khác hoặc `null`.

### Giá trị mặc định của field và phần tử mảng

Java gán mặc định `0` cho **field primitive `int`**, nhưng `null` cho **field kiểu `Integer`**:

~~~java
class Defaults {
    int primitiveCount;
    Integer optionalCount;
}

// Trong một phương thức:
Defaults value = new Defaults();
System.out.println(value.primitiveCount); // 0
System.out.println(value.optionalCount);  // null
~~~

Tương tự, `new int[3]` có các phần tử bằng 0; `new Integer[3]` có các phần tử bằng `null`. Biến cục bộ chưa gán không tự động được đọc với giá trị mặc định: trình biên dịch yêu cầu biến được gán chắc chắn (*definite assignment*) trước khi sử dụng.

Điểm này quan trọng với DTO, entity và các mô hình đầu vào: chọn `int` có thể làm mất khả năng biểu diễn “chưa cung cấp”; chọn `Integer` buộc code nhận dữ liệu phải quyết định cách xử lý `null`.

## 3. Boxing và unboxing có thể che giấu khác biệt null/0

**Boxing** chuyển giá trị primitive sang wrapper:

~~~java
int raw = 0;
Integer boxed = raw; // autoboxing, giá trị boxed là 0
~~~

**Unboxing** chuyển wrapper trở lại primitive:

~~~java
Integer boxed = Integer.valueOf(0);
int raw = boxed; // unboxing, raw là 0
~~~

Khi wrapper khác `null`, unboxing lấy giá trị primitive. Nếu wrapper là `null`, Java **ném `NullPointerException`** vì không có đối tượng nào để đọc giá trị bên trong.

~~~java
Integer count = null;

// Lệnh sau biên dịch được nhưng ném NullPointerException khi chạy:
// int primitive = count;
~~~

Phép chuyển đổi đó có thể xảy ra **ngầm**, ngay cả khi source code không viết `intValue()`:

~~~java
Integer count = null;

// Mỗi biểu thức sau đều đòi unbox count và sẽ ném NPE khi chạy:
// int next = count + 1;
// boolean positive = count > 0;
// boolean equalsZero = count == 0;
// int multiplied = count * 2;
~~~

Phân biệt lỗi unboxing với trường hợp giá trị là 0: với `Integer count = 0;`, các biểu thức trên hợp lệ và tính đúng theo số nguyên; với `count = null;`, Java không coi null là 0 để tiếp tục tính.

### Kiểm tra null trước khi dùng giá trị

~~~java
Integer count = null;

if (count == null) {
    System.out.println("Chưa có số lượng");
} else if (count == 0) {
    System.out.println("Số lượng bằng 0");
} else {
    System.out.println("Số lượng là " + count);
}
~~~

Đoạn trên in `Chưa có số lượng`. Trong nhánh sau `else`, ta biết chắc `count` khác `null` nên biểu thức `count == 0` có thể unbox an toàn.

## 4. Toán tử ==: kiểm tra tham chiếu hay so sánh số?

Ngữ nghĩa của `==` phụ thuộc **kiểu tĩnh của hai toán hạng**.

### Hai tham chiếu Integer

~~~java
Integer a = null;
Integer b = null;
Integer zero = Integer.valueOf(0);

System.out.println(a == b);    // true: cùng là null
System.out.println(a == zero); // false: null khác tham chiếu đối tượng
~~~

Khi cả hai toán hạng là wrapper tham chiếu, `==` kiểm tra **identity của tham chiếu**, không yêu cầu unboxing để so sánh giá trị.

Một ví dụ khác:

~~~java
Integer left = Integer.valueOf(1_000);
Integer right = Integer.valueOf(1_000);

System.out.println(left.equals(right)); // true
// Không dùng left == right để xác định hai giá trị số có bằng nhau.
~~~

`Integer.valueOf` bảo đảm cache ít nhất các giá trị từ −128 đến 127, và có thể cache thêm các giá trị khác. Vì vậy kết quả `==` giữa hai wrapper có giá trị bằng nhau không phải cách so sánh số ổn định.

### Một wrapper và một primitive

~~~java
Integer zero = 0;
System.out.println(zero == 0); // true: Integer bị unbox thành int
~~~

Ngược lại:

~~~java
Integer missing = null;
// System.out.println(missing == 0); // NPE khi chạy: unbox null.
~~~

Vì vậy `missing == null` là một phép kiểm tra tham chiếu an toàn, nhưng `missing == 0` là phép so sánh số cần unbox và **không** an toàn nếu tham chiếu có thể null.

**Thứ tự ưu tiên trong điều kiện:**

~~~java
Integer count = null;
boolean isKnownZero = count != null && count == 0;
System.out.println(isKnownZero); // false
~~~

`&&` có đánh giá ngắn mạch: khi `count != null` là `false`, vế sau không được thực thi. Đây là một mẫu điều kiện an toàn để kiểm tra “đã có số và số đó bằng 0”.

## 5. equals() và Objects.equals(): so sánh theo giá trị an toàn

`Integer.equals()` so sánh giá trị **giữa hai đối tượng Integer**, còn `java.util.Objects.equals(a, b)` là cách tiện lợi để xử lý cả trường hợp null:

~~~java
Integer missing = null;
Integer zero = Integer.valueOf(0);
Integer anotherZero = Integer.valueOf(0);

System.out.println(java.util.Objects.equals(missing, zero)); // false
System.out.println(java.util.Objects.equals(zero, anotherZero)); // true
System.out.println(java.util.Objects.equals(null, null)); // true
~~~

Giá trị `true` ở `Objects.equals(null, null)` chỉ nói rằng **hai tham chiếu đều thiếu** theo định nghĩa phép so sánh null-safe; không phải chúng bằng số 0.

Các lưu ý:

- `missing.equals(zero)` ném `NullPointerException` vì gọi phương thức trên null.
- `zero.equals(missing)` trả `false`; receiver `zero` khác null.
- `Objects.equals(missing, zero)` trả `false` an toàn.
- `Integer.valueOf(0).equals(Long.valueOf(0L))` trả `false` vì hai wrapper khác lớp dù cùng giá trị toán học 0.

Khi so sánh giá trị có thể null từ hai nguồn, `Objects.equals` thường rõ nghĩa hơn `==`. Nhưng nếu logic phải phân biệt các trạng thái “đều thiếu” và “đều có giá trị 0”, hãy kiểm tra null riêng rồi thực hiện so sánh nghiệp vụ.

## 6. Ba trạng thái thường gặp trong dữ liệu ứng dụng

Có thể cần phân biệt **ba trường hợp** thay vì chỉ hai:

| Trạng thái | Ví dụ | Ý nghĩa có thể có |
| --- | --- | --- |
| Không có trường/khóa | Request JSON không gửi `count`; `Map` không có key | Khách hàng không yêu cầu cập nhật trường |
| Có trường nhưng giá trị null | `{"count": null}`; `map.put("count", null)` | Khách hàng muốn xóa giá trị hoặc dữ liệu chưa biết |
| Có trường với giá trị 0 | `{"count": 0}`; `map.put("count", 0)` | Khách hàng khẳng định số lượng là 0 |

Cách hiểu phụ thuộc **hợp đồng API**. Với HTTP PATCH, việc không gửi field có thể mang nghĩa “giữ nguyên”, còn gửi `null` có thể mang nghĩa “xóa”; với HTTP POST, hai trường hợp có thể được validation xử lý khác. Đây là thiết kế API, không phải quy tắc cố định của mọi thư viện JSON.

Một biến `Integer count` riêng lẻ chỉ biểu diễn được **null hoặc một số**; nó không lưu được riêng trạng thái “field vắng mặt” so với “field có mặt và null”. Muốn phân biệt đầy đủ ba trạng thái, cần thêm metadata về sự hiện diện, một cấu trúc dữ liệu có `containsKey`, hoặc một kiểu dữ liệu được thiết kế rõ ràng cho yêu cầu cập nhật.

### Map.get() không phân biệt được key vắng mặt với mapping null

~~~java
java.util.Map<String, Integer> counts = new java.util.HashMap<>();
counts.put("explicitNull", null);
counts.put("zero", 0);

System.out.println(counts.get("absent"));       // null
System.out.println(counts.get("explicitNull")); // null
System.out.println(counts.get("zero"));         // 0
~~~

Hai lời gọi `get` đầu đều trả `null`, nhưng ý nghĩa khác nhau. Dùng `containsKey` để xác định key có tồn tại:

~~~java
System.out.println(counts.containsKey("absent"));       // false
System.out.println(counts.containsKey("explicitNull")); // true
System.out.println(counts.containsKey("zero"));         // true
~~~

Với `HashMap`, `getOrDefault` chỉ dùng giá trị mặc định khi **không có mapping cho key**; nếu key tồn tại và map tới null, kết quả vẫn là null:

~~~java
System.out.println(counts.getOrDefault("absent", -1));       // -1
System.out.println(counts.getOrDefault("explicitNull", -1)); // null
~~~

Không nên dùng `map.getOrDefault(key, 0)` như một giải pháp tổng quát để biến mọi null thành 0. Nó không xử lý key được map tới null, và chính việc tự chuyển dữ liệu thiếu thành 0 có thể trái với hợp đồng nghiệp vụ.

## 7. Chọn mô hình rõ ràng cho “không cung cấp số”

### Trường hợp 1: Giá trị luôn phải có

Dùng primitive như `int` và validation ở ranh giới nhận dữ liệu. Khi số lượng có thể là 0 nhưng không được thiếu, biểu diễn bằng primitive là hợp lý sau khi đã xác thực đầu vào.

~~~java
static int requireCount(Integer count) {
    if (count == null) {
        throw new IllegalArgumentException("count is required");
    }
    if (count < 0) {
        throw new IllegalArgumentException("count cannot be negative");
    }
    return count;
}
~~~

Đây là **phương thức Java** để đặt trong một lớp, chưa phải chương trình chạy độc lập. Nhánh `count < 0` chỉ chạy sau khi kiểm tra null, do đó unboxing an toàn. Nếu đầu vào cần cho phép số âm, bỏ điều kiện đó theo nghiệp vụ.

### Trường hợp 2: Giá trị có thể chưa biết

Dùng `Integer` cùng một nhánh xử lý null rõ ràng:

~~~java
static String describe(Integer count) {
    if (count == null) return "unknown";
    if (count == 0) return "none";
    return "count=" + count;
}
~~~

Phương thức này phân biệt “chưa biết” với “đã biết bằng 0”. Đừng dùng `count == null ? 0 : count` nếu bạn còn cần giữ sự khác biệt.

### Trường hợp 3: Muốn biểu thị thiếu giá trị bằng API chuyên dụng

`java.util.OptionalInt` có thể mô tả “có số nguyên” hoặc “không có số nguyên”:

~~~java
java.util.OptionalInt absent = java.util.OptionalInt.empty();
java.util.OptionalInt presentZero = java.util.OptionalInt.of(0);

System.out.println(absent.isPresent()); // false
System.out.println(presentZero.isPresent()); // true
System.out.println(presentZero.getAsInt()); // 0
~~~

`OptionalInt` loại nhu cầu dùng null cho chính giá trị optional này và tránh boxing của `Optional<Integer>`. Tuy nhiên, `absent.orElse(0)` **cố ý gộp** thiếu giá trị thành 0 khi lấy kết quả; chỉ làm vậy nếu nghiệp vụ cho phép.

`OptionalInt` phù hợp để thể hiện kết quả có/không có giá trị ở một số API. Với field entity, kiểu dữ liệu JSON, ORM hoặc thư viện serialization, nên chọn dạng được framework hỗ trợ rõ ràng và kiểm tra mapping thực tế; không mặc định mọi công cụ sẽ serialize Optional giống nhau.

## 8. Ternary, điều kiện và phương thức: unboxing ẩn

Toán tử điều kiện `condition ? a : b` có quy tắc xác định kiểu kết quả theo **kiểu các nhánh**. Khi trộn một wrapper với một primitive số cùng kiểu, Java có thể chọn kiểu primitive và unbox wrapper **chỉ ở nhánh được chọn**:

~~~java
Integer missing = null;
boolean useMissing = true;

// Đoạn này ném NullPointerException tại runtime:
int result = useMissing ? missing : 0;
~~~

Không có cách nào để ép Java tự hiểu `missing` là giá trị 0. Nếu muốn kết quả vẫn có khả năng null, phải chủ động dùng một biểu thức có kiểu tham chiếu và hợp đồng rõ ràng. Ví dụ:

~~~java
Integer missing = null;
boolean useMissing = true;
Integer selected = useMissing ? missing : Integer.valueOf(0);
System.out.println(selected); // null
~~~

Cũng cẩn thận với các hàm nhận primitive:

~~~java
static void printCount(int value) {
    System.out.println(value);
}

// Integer count = null;
// printCount(count); // NPE khi cố unbox trước khi gọi hàm.
~~~

Khi định nghĩa API nhận `Integer` hoặc trả `Integer`, người viết và người gọi phải hiểu liệu `null` là trạng thái hợp lệ hay vi phạm hợp đồng. Nếu một phương thức **luôn** trả số hợp lệ, kiểu trả về primitive tránh được khả năng trả null; nếu giá trị có thể vắng, hãy mô tả rõ và cân nhắc Optional hoặc kiểu kết quả biểu đạt trạng thái.

## 9. Phân biệt null và 0 trong JDBC, cơ sở dữ liệu

Trong SQL, `NULL` là dấu hiệu thiếu/không biết giá trị theo mô hình cơ sở dữ liệu; còn số `0` là giá trị số. Với một cột nullable, hai trường hợp thường cần được bảo toàn riêng.

Đặc biệt, `java.sql.ResultSet.getInt("quantity")` **trả 0 cho SQL NULL** theo hợp đồng JDBC. Để phân biệt, phải gọi `wasNull()` ngay sau getter tương ứng:

~~~java
// Đoạn minh họa bên trong mã đã có java.sql.ResultSet rs:
int raw = rs.getInt("quantity");
Integer quantity = rs.wasNull() ? null : raw;
~~~

Cần gọi `wasNull()` **ngay sau lần đọc cột đó**, vì nó phản ánh giá trị NULL của cột gần nhất được getter đọc. Nếu gọi các getter khác trước, thông tin có thể không còn tương ứng với `quantity`.

Một số driver/JDBC API có cách lấy object như `getObject(..., Integer.class)`, có thể trả null cho SQL NULL khi được hỗ trợ. Nên kiểm tra tài liệu và hành vi driver cụ thể, đặc biệt khi mapping sang DTO/ORM.

**Bài học nghiệp vụ:** nếu “không có số lượng tồn kho được báo cáo” và “tồn kho bằng 0” là hai trạng thái khác nhau, việc map thẳng SQL NULL vào primitive `int` hoặc lấy `getInt` mà bỏ qua `wasNull()` có thể làm mất dữ liệu quan trọng.

## 10. JSON, biểu mẫu và giá trị mặc định

Khi nhận dữ liệu từ JSON hoặc form, cần định nghĩa rõ các trường hợp:

- Field vắng: có dùng mặc định không, từ chối hay giữ nguyên giá trị cũ?
- Field có `null`: có hợp lệ không? Có nghĩa “xóa giá trị” không?
- Field có `0`: có phải giá trị hợp lệ hay vi phạm giới hạn tối thiểu?
- Field có chuỗi `"0"`: có cho phép chuyển đổi chuỗi sang số không?
- Field có chuỗi `"null"`: đó là chuỗi bốn ký tự, không phải Java `null` hay JSON `null`.

Các framework có thể có quy tắc deserialize, coercion, validation và default khác nhau. Không tự giả định Jackson, Gson, Spring Data Binding hoặc một thư viện khác luôn phân biệt đúng ba trạng thái khi ánh xạ mọi trường vào một `Integer` đơn giản.

Một ví dụ thiết kế:

| Payload | Hành vi giả định của API cập nhật |
| --- | --- |
| `{}` | Không thay đổi số lượng hiện có |
| `{"quantity": null}` | Xóa số lượng đã lưu, nếu được phép |
| `{"quantity": 0}` | Cập nhật số lượng thành 0 |
| `{"quantity": 5}` | Cập nhật số lượng thành 5 |

Đây là **quy ước API ví dụ**, không phải quy tắc tự động của Java hay JSON. Để triển khai đúng, phải lưu thông tin hiện diện của field và áp dụng validation theo hợp đồng.

## 11. Chương trình Java 17+ hoàn chỉnh

Tạo tệp `NullVsZeroDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.OptionalInt;

public class NullVsZeroDemo {
    static String describe(Integer count) {
        if (count == null) {
            return "missing";
        }
        if (count == 0) {
            return "zero";
        }
        return "nonzero: " + count;
    }

    public static void main(String[] args) {
        Integer absent = null;
        Integer zero = Integer.valueOf(0);

        System.out.println("absent is null: " + (absent == null));
        System.out.println("zero is null: " + (zero == null));
        System.out.println("absent equals zero: " + Objects.equals(absent, zero));
        System.out.println("zero equals 0: " + Objects.equals(zero, 0));

        System.out.println("describe absent: " + describe(absent));
        System.out.println("describe zero: " + describe(zero));
        System.out.println("describe five: " + describe(5));

        try {
            int primitive = absent; // NPE do unboxing null
            System.out.println(primitive);
        } catch (NullPointerException ex) {
            System.out.println("unboxing absent: NPE");
        }

        Map<String, Integer> counts = new HashMap<>();
        counts.put("explicitNull", null);
        counts.put("zero", 0);

        System.out.println("missing key present: " + counts.containsKey("absent"));
        System.out.println("null key present: " + counts.containsKey("explicitNull"));
        System.out.println("zero key present: " + counts.containsKey("zero"));
        System.out.println("default for absent: " + counts.getOrDefault("absent", -1));
        System.out.println("default for explicit null: " +
                counts.getOrDefault("explicitNull", -1));

        OptionalInt noCount = OptionalInt.empty();
        OptionalInt zeroCount = OptionalInt.of(0);
        System.out.println("optional absent present: " + noCount.isPresent());
        System.out.println("optional zero: " + zeroCount.getAsInt());
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac --release 17 NullVsZeroDemo.java
java NullVsZeroDemo
~~~

Kết quả stdout:

~~~text
absent is null: true
zero is null: false
absent equals zero: false
zero equals 0: true
describe absent: missing
describe zero: zero
describe five: nonzero: 5
unboxing absent: NPE
missing key present: false
null key present: true
zero key present: true
default for absent: -1
default for explicit null: null
optional absent present: false
optional zero: 0
~~~

Giải thích:

1. `absent == null` chỉ kiểm tra **tham chiếu**, trong khi `zero` trỏ tới wrapper hợp lệ chứa số 0.
2. `Objects.equals(absent, zero)` trả false mà không gây NPE; số 0 chỉ bằng một giá trị số 0 cùng ngữ nghĩa phù hợp.
3. `describe` chủ động bảo toàn ba trạng thái: thiếu, bằng 0, khác 0.
4. Ép `absent` thành `int` thất bại khi chạy, cho thấy unboxing không thay null bằng 0.
5. `HashMap.containsKey` phân biệt key vắng với key tồn tại được map tới null; `getOrDefault` chỉ lấy mặc định cho key vắng.
6. `OptionalInt.empty()` và `OptionalInt.of(0)` phân biệt thiếu giá trị với giá trị 0, không cần tham chiếu null bên trong optional.

## 12. Các kiểu wrapper khác cũng có cùng vấn đề

### Long, Short, Byte

~~~java
Long absentId = null;
Long idZero = 0L;
System.out.println(absentId == null); // true
System.out.println(idZero.longValue() == 0L); // true
~~~

Nếu có `Long id = null;`, các phép cộng, so sánh số học hoặc unboxing xuống `long` sẽ ném NPE tương tự `Integer`. Không nên sử dụng số 0 làm “giá trị không tồn tại” trừ khi hợp đồng dữ liệu đã khẳng định 0 **không thể là giá trị hợp lệ**.

### Double và Float

~~~java
Double absentMeasurement = null;
Double zeroMeasurement = 0.0;

System.out.println(absentMeasurement == null); // true
System.out.println(zeroMeasurement == null);    // false
~~~

Đối với floating point, còn có `+0.0` và `-0.0`. Cả hai là giá trị số thực hợp lệ, **đều khác `null`**. Phép toán số thực primitive `+0.0 == -0.0` trả true, trong khi `Double.equals()` phân biệt zero có dấu. Đây là câu hỏi **bình đẳng floating point**, tách biệt với việc kiểm tra tham chiếu null.

`Double.NaN` cũng **không phải null**. NaN đại diện một kết quả dấu phẩy động không xác định theo IEEE 754; đó vẫn là giá trị nằm trong một object `Double` nếu được boxing. Nếu ứng dụng còn cần phân biệt “thiếu số đo”, “NaN do phép toán” và “giá trị số 0”, phải quy định riêng từng trường hợp.

### Boolean: false khác null

Dù không phải số, `Boolean` là minh họa rất gần:

~~~java
Boolean noResponse = null;
Boolean explicitlyFalse = Boolean.FALSE;

System.out.println(noResponse == null);      // true
System.out.println(Boolean.FALSE.equals(noResponse)); // false
~~~

Một field có thể mang trạng thái “chưa trả lời”, “đã trả lời không”, “đã trả lời có”. Dùng primitive `boolean` sẽ không lưu được trạng thái chưa trả lời bằng null.

## 13. Khi nào được thay null bằng 0?

Chuyển giá trị thiếu sang 0 không phải lúc nào cũng sai. Nó phù hợp khi **hợp đồng nghiệp vụ xác định** thiếu dữ liệu tương đương số 0. Ví dụ một hàm thống kê tổng tiền của các loại phí tùy chọn có thể coi phí vắng mặt là 0.

~~~java
static int orZero(Integer value) {
    return value == null ? 0 : value;
}
~~~

Phương thức này làm mất sự khác biệt giữa null và 0 **có chủ đích**. Đó phải là quyết định rõ ràng tại ranh giới xử lý, không phải mặc định áp dụng trong mọi tầng hệ thống.

Cần tránh:

~~~java
// Mẫu dễ gây sai ý nghĩa nếu "chưa biết" khác "bằng 0":
// Integer stock = repository.findStock(...);
// int safeStock = stock == null ? 0 : stock;
~~~

Nếu `null` có nghĩa “chưa kiểm kê”, biến `safeStock` có thể bị hiểu nhầm thành “chắc chắn hết hàng”. Thay vào đó, giữ nullable value, tạo trạng thái enum rõ ràng, hoặc trả về một kết quả có cấu trúc chứa cả tình trạng xác thực.

**Nguyên tắc:** chỉ gộp trạng thái khi biết rõ người sử dụng kết quả cần ngữ nghĩa nào.

## 14. Lỗi thường gặp và cách tránh

| Cách viết/thói quen | Rủi ro | Cách đúng |
| --- | --- | --- |
| `Integer x = null; int y = x;` | NPE do unboxing | Kiểm tra null hoặc đặt hợp đồng non-null |
| `Integer x = null; x == 0` | NPE do so sánh số | `x != null && x == 0` |
| `x.equals(0)` khi `x` nullable | NPE nếu x null | `Objects.equals(x, 0)` hoặc kiểm tra null |
| `Integer a, b; a == b` để so giá trị | Phụ thuộc identity/cache | `Objects.equals(a, b)` |
| Coi mọi `Integer` null là 0 | Mất nghĩa “chưa biết” | Chỉ gán mặc định khi nghiệp vụ cho phép |
| `map.get(key) == null` nghĩa là key vắng | Không phân biệt key tồn tại với mapping null | `map.containsKey(key)` |
| `map.getOrDefault(key, 0)` xử lý mọi null | Mapping tới null vẫn trả null | Xác định chính sách cho key vắng và null riêng |
| `ResultSet.getInt` là đủ để đọc nullable SQL integer | SQL NULL cũng trả 0 | Gọi ngay `ResultSet.wasNull()` |
| Dùng primitive field khi cần biết JSON field có mặt không | Không biểu diễn được null; còn mất thông tin “absent” | Theo dõi sự hiện diện và hợp đồng deserialize |
| Coi chuỗi `"0"` bằng số 0 trước parse | Không cùng kiểu dữ liệu | Parse/validate theo định dạng đầu vào |
| Gọi `OptionalInt.orElse(0)` rồi quên trạng thái absent | Cố ý mất thông tin thiếu | Dùng `isPresent()` hoặc xử lý nhánh absent trước |
| Đánh đồng `Double.NaN`, `0.0` và `null` | Ba trường hợp có ngữ nghĩa khác nhau | Kiểm tra `null`, `Double.isNaN` và giá trị 0 riêng |

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Hai dòng sau có giống nhau không?

~~~java
Integer a = null;
Integer b = 0;
~~~

**Đáp án:** Không. `a` không trỏ tới object; `b` trỏ tới một `Integer` đại diện số 0. `a == null` true; `b == null` false.

**Câu 2.** Vì sao `Integer count = null; if (count == 0) ...` ném lỗi?

**Đáp án:** Toán hạng `0` là primitive `int`, khiến Java unbox `count` để so sánh giá trị. Unboxing tham chiếu null gây `NullPointerException`.

**Câu 3.** `Objects.equals(null, null)` trả true có nghĩa null bằng 0 không?

**Đáp án:** Không. Nó chỉ cho biết hai đối số cùng là null. `Objects.equals(null, 0)` trả false.

**Câu 4.** Trong `HashMap`, `get("x")` trả null có chứng minh không có key x không?

**Đáp án:** Không. Key có thể tồn tại và được map tới null. Dùng `containsKey("x")` để phân biệt.

**Câu 5.** Nếu cột SQL chứa NULL, `ResultSet.getInt("quantity")` trả gì và phải kiểm tra điều gì?

**Đáp án:** Nó trả primitive 0. Gọi ngay `wasNull()` để phân biệt SQL NULL với giá trị số 0 thực sự.

**Câu 6.** Khi nào dùng `Integer` thay `int`?

**Đáp án:** Khi cần API object/generic hoặc cần diễn tả trạng thái có thể thiếu giá trị; nếu dữ liệu bắt buộc có số và không cần biểu diễn null, `int` thường đơn giản hơn.

**Câu 7.** `OptionalInt.empty().orElse(0)` và `OptionalInt.of(0).orElse(0)` cùng trả 0. Có còn phân biệt trạng thái đầu vào không?

**Đáp án:** Không, vì lời gọi `orElse(0)` đã cố ý chuyển cả hai thành primitive 0. Nếu cần phân biệt, hãy dùng `isPresent()`/nhánh xử lý trước.

## 16. Ghi nhớ và tham khảo

- **`null` biểu thị không có object; số `0` biểu thị một giá trị hợp lệ**. Đây là khác biệt dữ liệu và nghiệp vụ, không chỉ cú pháp.
- **Primitive không chứa null; wrapper có thể chứa null**. Tự động unboxing null sẽ ném `NullPointerException`.
- **`== null` kiểm tra tham chiếu; `== 0` với wrapper yêu cầu unboxing**. Dùng null guard hoặc `Objects.equals` đúng ngữ cảnh.
- **`Map.get`, JDBC `getInt` và việc deserialize field** có thể làm mất thông tin nếu không xử lý trạng thái thiếu một cách chủ đích.
- Dùng `OptionalInt` hoặc cấu trúc kết quả có thông tin hiện diện khi hợp đồng API yêu cầu. Chỉ chuyển null thành 0 khi nghiệp vụ cho phép.

Tài liệu Java 17:

- [Java Language Specification — Boxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7) và [Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.8).
- [Java Language Specification — Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21).
- [Integer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html) và [Objects.equals API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)).
- [Map API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html) và [OptionalInt API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalInt.html).
- [JDBC ResultSet API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): `getInt` và `wasNull`.
