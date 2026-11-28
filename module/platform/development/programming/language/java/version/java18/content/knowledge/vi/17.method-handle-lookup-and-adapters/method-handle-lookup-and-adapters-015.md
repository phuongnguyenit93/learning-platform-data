# asCollector(): gom tham số vào mảng và kiểm tra số lượng phần tử

## 1. Tình huống: method đích nhận mảng nhưng caller có nhiều đối số riêng lẻ

Giả sử một thư viện Java cung cấp phương thức nhận nhãn và mảng chuỗi:

~~~java
public static String render(String label, String[] items) {
    return label + ": " + String.join(", ", items);
}
~~~

Phương thức đích nhận đúng **hai tham số**: `String label` và `String[] items`. Nhưng tại một điểm gọi động, ứng dụng có sẵn các giá trị riêng lẻ `"A"`, `"B"`, `"C"`. Làm thế nào để gọi được một `MethodHandle` nhận các giá trị rời đó mà không tự tạo `new String[] {...}` ở mỗi nơi gọi?

API `MethodHandle.asCollector(Class<?> arrayType, int arrayLength)` tạo một **handle adapter**. Adapter nhận một số đối số thành phần đã được ấn định, gom chúng thành một mảng, rồi truyền mảng ấy vào vị trí tham số mảng cuối cùng của method handle gốc.

~~~text
Method đích:                  render(String, String[])
Handle ban đầu:               (String,String[])String

asCollector(String[].class, 3)
               |
               v
Handle sau khi thích nghi:     (String,String,String,String)String
                                 label item[0] item[1] item[2]
               |
               v
Đóng gói:                     String[] {"A", "B", "C"}
               |
               v
Gọi đích:                     render("batch", items)
~~~

**Con số `3` trong `asCollector(String[].class, 3)` là số phần tử được gom vào mảng**, không phải tổng số tham số của handle sau chuyển đổi. Handle cuối cùng có bốn tham số vì nó vẫn giữ tham số `label`.

Bài thuộc chương **Lookup và adapter** của module Java 18. `MethodHandle` và `asCollector` là API công khai vẫn dùng được trên JDK hiện đại; bài tập trung vào hợp đồng kiểu, số lượng đối số và cách xử lý lỗi hiện hành.

## 2. Phân biệt kiểu handle trước và sau asCollector

`MethodType` mô tả kiểu trả về và toàn bộ kiểu tham số của một handle theo đúng thứ tự.

~~~java
import java.lang.invoke.MethodType;

MethodType original = MethodType.methodType(
        String.class, String.class, String[].class);

System.out.println(original); // (String,String[])String
~~~

Khi phương thức `render` được tìm bằng `findStatic`, handle có `type()` giống `original`. Gọi:

~~~java
MethodHandle collect3 = originalHandle.asCollector(String[].class, 3);
System.out.println(collect3.type());
// (String,String,String,String)String
~~~

Ý nghĩa của hai kiểu:

| Giá trị | Tham số mà caller phải cung cấp | Tham số method đích nhận |
| --- | --- | --- |
| Handle gốc: `(String,String[])String` | Một `String` và một `String[]` | Một `String` và một `String[]` |
| Collector 0 phần tử: `(String)String` | Một `String` | Một `String` và mảng rỗng `String[0]` |
| Collector 1 phần tử: `(String,String)String` | Hai `String` | Một `String` và mảng `String[1]` |
| Collector 3 phần tử: `(String,String,String,String)String` | Bốn `String` | Một `String` và mảng `String[3]` |

`asCollector` trả về **một MethodHandle mới**. Nó không thay chữ ký của method Java đã được khai báo và không sửa kiểu của `originalHandle`. Có thể giữ nhiều collector khác nhau cùng trỏ đến một handle gốc.

## 3. Hai đối số arrayType và arrayLength

Overload thường dùng là:

~~~java
MethodHandle adapted = target.asCollector(
        String[].class,
        3);
~~~

Hai tham số của `asCollector` có ý nghĩa khác nhau:

- `arrayType` là **kiểu mảng được tạo để gom phần tử**, ví dụ `String[].class` hoặc `int[].class`. Phải là kiểu mảng hợp lệ, tương thích với tham số mảng tại vị trí cần gom trên handle đích.
- `arrayLength` là **số lượng đối số thành phần** sẽ thay thế tham số mảng. Số này được xác định ngay khi tạo adapter, phải không âm và phải thỏa giới hạn kiểu phương thức của JVM.

Với overload hai đối số, **vị trí gom là tham số cuối cùng** của handle gốc. Ví dụ với `render(String, String[])`, tham số `label` vẫn đứng đầu; chỉ `String[]` được thay bằng nhiều `String`.

Nếu muốn gom một mảng tại vị trí khác, các JDK hiện đại có overload `asCollector(int collectArgPos, Class<?> arrayType, int arrayLength)`, được trình bày ở phần 7.

### Độ dài bằng 0 là hợp lệ

~~~java
MethodHandle collect0 = originalHandle.asCollector(
        String[].class, 0);
~~~

Handle này nhận **không phần tử nào** cho mảng, nhưng vẫn nhận các tham số khác của handle gốc. Khi gọi `render("batch", ...)`, adapter tạo mảng `String[0]`. Kết quả `render` có thể là `"batch: "`.

Vì vậy “gom 0 phần tử” khác với việc “không gọi method đích”: **method đích vẫn được gọi** và nhận mảng rỗng ở vị trí mảng.

## 4. Ví dụ Java đầy đủ: tạo collector và thử 0, 1, 3 phần tử

Lưu chương trình dưới tên `AsCollectorDemo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class AsCollectorDemo {

    public static String render(String label, String[] items) {
        return label + ": " + String.join(", ", items);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodType declared = MethodType.methodType(
                String.class, String.class, String[].class);

        MethodHandle base = lookup.findStatic(
                AsCollectorDemo.class, "render", declared);

        MethodHandle collect0 = base.asCollector(String[].class, 0);
        MethodHandle collect1 = base.asCollector(String[].class, 1);
        MethodHandle collect3 = base.asCollector(String[].class, 3);

        System.out.println("base     = " + base.type());
        System.out.println("collect0 = " + collect0.type());
        System.out.println("collect1 = " + collect1.type());
        System.out.println("collect3 = " + collect3.type());

        String a = (String) collect0.invokeExact("batch");
        String b = (String) collect1.invokeExact("batch", "A");
        String c = (String) collect3.invokeExact(
                "batch", "A", "B", "C");

        System.out.println(a);
        System.out.println(b);
        System.out.println(c);

        try {
            // Thiếu một phần tử: call site có 3 tham số, handle có 4.
            String wrong = (String) collect3.invokeExact(
                    "batch", "A", "B");
            System.out.println(wrong);
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrong number of arguments");
        }

        // Handle gốc vẫn nhận một mảng hoàn chỉnh.
        String original = (String) base.invokeExact(
                "batch", new String[] {"A", "B", "C"});
        System.out.println(original);
    }
}
~~~

Biên dịch và chạy bằng JDK hiện đại:

~~~bash
javac AsCollectorDemo.java
java AsCollectorDemo
~~~

Đầu ra dự kiến:

~~~text
base     = (String,String[])String
collect0 = (String)String
collect1 = (String,String)String
collect3 = (String,String,String,String)String
batch:
batch: A
batch: A, B, C
wrong number of arguments
batch: A, B, C
~~~

Dòng `batch:` được in ra với một dấu cách ở cuối do implementation `render` ghép `": "`. Khi quan sát output ở terminal, dấu cách cuối dòng có thể khó nhận ra; đây không ảnh hưởng đến ý nghĩa của mảng rỗng.

**Hai kết luận từ ví dụ:** `asCollector` không làm biến mất tham số `label`, và collector có `arrayLength = 3` yêu cầu chính xác ba phần tử riêng lẻ để tạo mảng ở mỗi lượt gọi.

## 5. Kiểm tra số lượng phần tử ở hai thời điểm khác nhau

Cần phân biệt **lỗi khi tạo adapter** với **lỗi khi gọi adapter**.

### Khi tạo adapter

~~~java
MethodHandle collect2 = base.asCollector(String[].class, 2);
~~~

JDK kiểm tra các điều kiện của kiểu mảng, vị trí tham số và độ dài cần gom. Nếu chúng không hợp lệ, việc tạo collector có thể ném `IllegalArgumentException` (hoặc `NullPointerException` khi kiểu mảng truyền vào là `null` theo hợp đồng API).

Ví dụ một yêu cầu số phần tử âm không hợp lệ:

~~~java
try {
    base.asCollector(String[].class, -1);
    throw new AssertionError("Expected IllegalArgumentException");
} catch (IllegalArgumentException expected) {
    System.out.println("negative arrayLength is invalid");
}
~~~

### Khi gọi adapter

Sau khi tạo thành công `collect2`, kiểu của nó đã được ấn định là:

~~~text
(String,String,String)String
        |      |
       item0  item1
~~~

Với `invokeExact`, **call site phải khớp chính xác kiểu tham số và kiểu trả về** của `collect2`. Nếu chỉ đưa một item:

~~~java
try {
    String result = (String) collect2.invokeExact("batch", "A");
    System.out.println(result);
} catch (java.lang.invoke.WrongMethodTypeException expected) {
    System.out.println("Expected two collected items");
}
~~~

Lỗi đến từ kiểu lời gọi `(String,String)String` không khớp `(String,String,String)String`; phương thức `render` chưa nhận được mảng hai phần tử.

Tương tự, truyền **nhiều hơn** hai item cũng khiến call site `invokeExact` không khớp số tham số của collector:

~~~java
// Minh họa lời gọi sai kiểu, không chạy qua target:
// String result = (String) collect2.invokeExact(
//         "batch", "A", "B", "C");
~~~

Không có chuyện collector “tự chọn” hai trong ba item rồi bỏ item còn lại. **Số phần tử là một phần của cấu trúc MethodType được tạo khi gọi asCollector.**

## 6. Hai loại lỗi khác nhau: sai độ dài và sai kiểu phần tử

`arrayLength` quy định số lượng phần tử; `arrayType` quy định kiểu từng phần tử.

Giả sử `collect2` mong chờ:

~~~text
(String,String,String)String
 label  item0  item1
~~~

Mỗi phần tử thu gom phải là `String` tại call site của `invokeExact`. Ví dụ:

~~~java
String ok = (String) collect2.invokeExact(
        "batch", "A", "B");
~~~

Nhưng:

~~~java
// int khác String, dù số lượng tham số đúng.
String wrong = (String) collect2.invokeExact(
        "batch", 123, "B");
~~~

Lời gọi thứ hai dẫn tới `WrongMethodTypeException` vì kiểu của đối số thứ hai là `int`, còn handle mong đợi `String`. Vấn đề ở đây là **kiểu phần tử**, không phải độ dài mảng.

Nếu dùng `invoke(...)`, một số phép chuyển đổi/thích nghi kiểu có thể xảy ra theo hợp đồng MethodHandle; lỗi khi thích nghi vẫn có thể xuất hiện. Đừng dựa vào `invoke(...)` để ngầm sửa dữ liệu sai kiểu hoặc bỏ qua số lượng đối số: thiết kế thư viện nên kiểm tra metadata và validation trước khi thực thi.

### Primitive array cũng hoạt động

`asCollector` không giới hạn ở mảng của reference type. Với phương thức nhận `int[]`:

~~~java
import java.util.Arrays;

public static int sum(int[] numbers) {
    return Arrays.stream(numbers).sum();
}
~~~

Adapter tương ứng:

~~~java
MethodHandle base = MethodHandles.lookup().findStatic(
        AsCollectorDemo.class,
        "sum",
        MethodType.methodType(int.class, int[].class));

MethodHandle sum3 = base.asCollector(int[].class, 3);
// sum3.type(): (int,int,int)int

int total = (int) sum3.invokeExact(2, 3, 5);
System.out.println(total); // 10
~~~

Hai đoạn trên là phần mở rộng để thêm vào `AsCollectorDemo`; cần có `sum` là static method trong cùng lớp và import `Arrays`. Với `int[].class`, các đối số thành phần của collector có kiểu `int`, không phải `Integer` theo `invokeExact`.

## 7. Gom mảng ở vị trí không phải tham số cuối

Trên các JDK hiện đại, có thể chỉ rõ vị trí tham số mảng bằng:

~~~java
MethodHandle adapted = target.asCollector(
        int collectArgPos,
        Class<?> arrayType,
        int arrayLength);
~~~

Ví dụ method đích có mảng ở **vị trí 0**, theo sau bởi một số nguyên:

~~~java
public static String repeat(String[] words, int times) {
    return String.join("-", words).repeat(times);
}
~~~

Kiểu gốc là:

~~~text
(String[],int)String
~~~

Tạo collector ở vị trí 0:

~~~java
MethodHandle base = MethodHandles.lookup().findStatic(
        AsCollectorDemo.class,
        "repeat",
        MethodType.methodType(String.class, String[].class, int.class));

MethodHandle collect2 = base.asCollector(0, String[].class, 2);

System.out.println(collect2.type());
// (String,String,int)String

String result = (String) collect2.invokeExact("A", "B", 2);
System.out.println(result); // A-BA-B
~~~

`collectArgPos = 0` chỉ định tham số mảng trong `base.type()`, không phải vị trí item đầu tiên trong một cấu trúc dữ liệu khác. Adapter nhận lần lượt hai `String` để tạo `String[]` tại vị trí 0, rồi giữ tham số `int times` ở phía sau.

Đoạn mã này cũng là phần mở rộng cho lớp `AsCollectorDemo`, không phải file Java độc lập mới.

Cần lưu ý:

- Vị trí đếm từ **0**, giống nhiều API Java.
- Vị trí được chỉ định phải là vị trí tham số có thể nhận kiểu mảng phù hợp.
- `arrayLength` chỉ thay đúng một tham số mảng thành một chuỗi tham số thành phần, không tự thu gom các tham số khác.
- Overload hai đối số `asCollector(arrayType, arrayLength)` tiện hơn khi mảng ở cuối; overload ba đối số cho phép kiểm soát vị trí rõ ràng.

## 8. Mô hình kiểu tổng quát

Giả sử handle gốc có kiểu:

~~~text
(P0, ..., Pk-1, ArrayType, Pk+1, ..., Pn)Return
                     ^
              collectArgPos = k
~~~

Sau `asCollector(k, ArrayType.class, m)`, khi kiểu phần tử mảng là `E`:

~~~text
(P0, ..., Pk-1, E, E, ... m lần ..., E, Pk+1, ..., Pn)Return
~~~

Tổng số tham số mới là:

\[
\text{newParameterCount} = \text{originalParameterCount} - 1 + m
\]

Ví dụ `(String,String[])String` có 2 tham số; khi gom 3 phần tử:

\[
2 - 1 + 3 = 4
\]

Khi gom 0 phần tử:

\[
2 - 1 + 0 = 1
\]

Đây là công thức **số tham số trong MethodType**, không phải tổng số ô (slot) kiểu JVM của tất cả tham số. Kiểu `long` và `double` chiếm hai slot trong descriptor JVM; khi sinh chữ ký lớn, JDK còn phải kiểm tra giới hạn slot cho method type. Vì vậy một số `arrayLength` không âm vẫn có thể bị từ chối nếu làm kiểu phương thức vượt giới hạn được hỗ trợ.

## 9. Khác nhau giữa asCollector, asSpreader và asVarargsCollector

Ba API đều liên quan đến array, nhưng không thay thế lẫn nhau:

| API | Biến đổi ý tưởng | Ví dụ |
| --- | --- | --- |
| `asCollector(String[].class, 2)` | Nhiều đối số `String` riêng lẻ → một `String[]` để gọi target | `(String,String[])String` → `(String,String,String)String` |
| `asSpreader(String[].class, 2)` | Một `String[]` ở call site → hai đối số `String` của target | `(String,String,String)String` → `(String,String[])String` |
| `asVarargsCollector(String[].class)` | Tạo handle có hành vi thu gom varargs ở các kiểu lời gọi phù hợp | Cho phép cơ chế gọi varargs linh hoạt hơn `asCollector` cố định độ dài |

`asCollector` tạo một **hình dạng tham số cố định**. Số phần tử phải được chọn khi tạo adapter. `asVarargsCollector` phù hợp hơn khi API cần hỗ trợ cách gọi nhiều phần tử ở các arity khác nhau theo cơ chế varargs của method handle.

`asSpreader` chuyển theo hướng ngược lại về mặt hình dạng tham số, nhưng cũng có các kiểm tra kiểu và độ dài riêng. Không đồng nhất hai API với việc Java biên dịch bình thường xử lý cú pháp `String...`: đây là những biến đổi động trên `MethodHandle`.

### Ví dụ kiểm chứng hai chiều với asSpreader

Giả sử đã có `collect2`:

~~~java
MethodHandle collect2 = base.asCollector(String[].class, 2);
// (String,String,String)String

MethodHandle spreadAgain = collect2.asSpreader(String[].class, 2);
// (String,String[])String

String value = (String) spreadAgain.invokeExact(
        "batch", new String[] {"A", "B"});
System.out.println(value); // batch: A, B
~~~

Ví dụ này minh họa hai biến đổi kiểu đối xứng về số tham số và giá trị trong trường hợp đơn giản; không nên suy rằng mọi chuỗi adapter đều triệt tiêu toàn bộ hiệu ứng, hiệu năng hoặc hành vi phụ của từng adapter.

## 10. Nên kiểm tra handle.type() trước khi invoke

Trong thư viện tạo method handle từ metadata động, in `type()` là một cách chẩn đoán ngắn gọn. Nó xác nhận cả số lượng và thứ tự kiểu tham số.

~~~java
MethodHandle collector = base.asCollector(String[].class, 3);

MethodType t = collector.type();
System.out.println(t.returnType());          // class java.lang.String
System.out.println(t.parameterCount());      // 4
System.out.println(t.parameterType(0));      // class java.lang.String
System.out.println(t.parameterType(1));      // class java.lang.String
System.out.println(t.parameterType(2));      // class java.lang.String
System.out.println(t.parameterType(3));      // class java.lang.String
~~~

Muốn kiểm tra một schema dự kiến:

~~~java
MethodType required = MethodType.methodType(
        String.class,
        String.class, String.class, String.class, String.class);

if (!collector.type().equals(required)) {
    throw new IllegalStateException(
            "Unexpected collector type: " + collector.type());
}
~~~

Bước này hữu ích khi gọi `invokeExact`: toàn bộ kiểu tham số và kiểu trả về tại call site phải khớp `MethodType`. Không cần cố gọi để “thử từng arity” nếu đã có thông tin loại kiểu từ `handle.type()`.

## 11. Khi áp dụng trong dispatcher và API plugin

Giả sử một hệ thống nhận dữ liệu JSON gồm `label` và danh sách `items`. Tùy cấu hình, nó cần gọi method đích `render(String, String[])` bằng một số phần tử cụ thể.

Quy trình phù hợp:

1. **Xác định method đích và chữ ký:** dùng lookup với `MethodType.methodType(String.class, String.class, String[].class)`, kiểm tra quyền truy cập của member.
2. **Xác định số phần tử cần thu gom:** ví dụ số item của một lệnh cụ thể là `3`.
3. **Tạo collector với kích thước đó:** `base.asCollector(String[].class, 3)`.
4. **Kiểm tra kiểu handle tạo ra:** `collector.type()` phải phù hợp với cách ứng dụng chuẩn bị đối số.
5. **Gọi với đúng số lượng và kiểu dữ liệu:** chọn `invokeExact` khi đã biết chính xác chữ ký tại call site, hoặc một API gọi thích hợp cho tình huống dữ liệu runtime sau khi đã validation.

**Không cần tự động tạo collector mới cho từng request** nếu một request có thể gọi thẳng handle nhận `String[]`. Trong tình huống số phần tử thay đổi rất thường xuyên, giữ handle nhận mảng và truyền mảng có sẵn có thể đơn giản hơn việc tạo nhiều collector cố định. Chọn adapter vì nó giúp thỏa hợp đồng gọi cụ thể, không vì cho rằng nó luôn nhanh hơn.

Nếu cache collector theo độ dài, hãy cân nhắc giới hạn số kích thước được cache và vòng đời class loader để tránh giữ tài nguyên lâu không cần thiết. Nội dung bài tập trung vào hợp đồng API; đo hiệu năng phải dựa trên workload và JDK mục tiêu.

## 12. Bảng lỗi thường gặp và cách phân biệt

| Hiện tượng | Nguyên nhân cần xem xét | Cách kiểm chứng |
| --- | --- | --- |
| `IllegalArgumentException` ngay khi gọi `asCollector` | `arrayType` không phải array, không tương thích với tham số tại vị trí thu gom, `arrayLength` không hợp lệ hoặc vượt giới hạn kiểu | In `base.type()`; kiểm tra vị trí mảng, kiểu mảng và độ dài. |
| `WrongMethodTypeException` ở `invokeExact` khi thiếu item | Call site có ít tham số hơn kiểu collector | In `collector.type()` và kiểm tra đúng số item. |
| `WrongMethodTypeException` ở `invokeExact` khi thừa item | Call site có nhiều tham số hơn kiểu collector | Kiểm tra số phần tử đã dùng khi tạo collector. |
| `WrongMethodTypeException` dù đủ số item | Kiểu từng item hoặc kiểu trả về tại call site không khớp | So sánh `collector.type()` với call-site MethodType; chú ý primitive và wrapper. |
| `NoSuchMethodException` tại `findStatic` | Tên hoặc `MethodType` khai báo không khớp method đích | Kiểm tra return type và thứ tự parameter types. |
| `IllegalAccessException` tại lookup | Lookup thiếu quyền truy cập method đích | Kiểm tra quyền JPMS, class và member; adapter không cấp thêm quyền. |
| Method đích ném exception nghiệp vụ | Adapter đã chuyển đối số đến target; target tự ném lỗi | Ghi nhận exception gốc và kiểm tra logic nghiệp vụ riêng. |
| Không thể gọi `asCollector` trên handle không có tham số mảng phù hợp | Chưa có vị trí nhận array | Xem `base.type()`, thay đổi thiết kế method hoặc chọn adapter khác thích hợp. |

Một lỗi `WrongMethodTypeException` không chứng minh method đích đã được thực thi. Lỗi kiểu tại call site có thể xuất hiện trước khi `render` được gọi. Để kiểm chứng hành vi, nên có test xác nhận một đường gọi đúng và các test âm riêng cho thiếu/thừa số lượng phần tử.

## 13. Bộ thử nghiệm đối chiếu đáng dùng

Trên cùng một JDK hiện đại, chạy các trường hợp sau với handle `base` nhận `(String,String[])String`:

| Test | Tạo adapter | Lời gọi | Kết quả mong đợi |
| --- | --- | --- | --- |
| Không gom phần tử | `asCollector(String[].class, 0)` | `invokeExact("batch")` với return `String` | Thành công, target nhận mảng rỗng. |
| Một phần tử | `asCollector(String[].class, 1)` | `invokeExact("batch", "A")` | Thành công, target nhận mảng dài 1. |
| Hai phần tử | `asCollector(String[].class, 2)` | `invokeExact("batch", "A", "B")` | Thành công, target nhận mảng dài 2. |
| Thiếu một phần tử | `asCollector(String[].class, 2)` | `invokeExact("batch", "A")` | `WrongMethodTypeException`. |
| Thừa một phần tử | `asCollector(String[].class, 2)` | `invokeExact("batch", "A", "B", "C")` | `WrongMethodTypeException`. |
| Số phần tử âm | `asCollector(String[].class, -1)` | Chưa gọi target | Adapter bị từ chối. |
| Loại mảng không tương thích | `asCollector(int[].class, 2)` | Chưa gọi target | Adapter bị từ chối. |
| Đúng array nhưng sai kiểu item | `asCollector(String[].class, 2)` | `invokeExact("batch", 10, "B")` | `WrongMethodTypeException`. |
| Gom ở vị trí 0 | `asCollector(0, String[].class, 2)` trên handle nhận `(String[],int)String` | `invokeExact("A", "B", 2)` | Thành công, target nhận `String[]{"A", "B"}` và `2`. |

Trong test thực tế, sử dụng biểu thức nhận kết quả có đúng kiểu trả về. Ví dụ, lời gọi `invokeExact` đến handle trả về `String` cần ngữ cảnh tương ứng:

~~~java
String text = (String) collector.invokeExact(
        "batch", "A", "B");
~~~

Nếu vô tình viết:

~~~java
collector.invokeExact("batch", "A", "B");
~~~

trong một câu lệnh không sử dụng kết quả, kiểu trả về mà call site yêu cầu có thể là `void`, dẫn đến `WrongMethodTypeException` dù ba đối số đã đúng. Đây là lỗi **kiểu trả về tại call site**, không phải lỗi gom phần tử.

## 14. Câu hỏi tự kiểm tra

1. Với handle gốc `(String,int[])long`, `asCollector(int[].class, 4)` tạo ra handle có bao nhiêu tham số? Liệt kê tất cả kiểu theo thứ tự.
2. Với handle gốc `(String,String[])String`, collector có `arrayLength = 0` có gọi được target không? Target sẽ nhận gì?
3. Vì sao `asCollector(String[].class, 3)` không có nghĩa collector luôn có ba tham số tổng cộng?
4. Vì sao một collector cố định `arrayLength = 2` không được âm thầm nhận ba item rồi bỏ item cuối?
5. Khi `invokeExact` ném `WrongMethodTypeException`, làm thế nào phân biệt sai số item với sai kiểu phần tử hoặc sai return type?
6. Với phương thức `repeat(String[] words, int times)`, tại sao overload hai đối số của `asCollector` không phù hợp bằng overload có `collectArgPos = 0`?
7. `asCollector` khác `asSpreader` về chiều biến đổi kiểu như thế nào?
8. Nếu số phần tử thay đổi theo từng request JSON, khi nào nên giữ handle nhận trực tiếp `String[]` thay vì tạo nhiều collector?
9. Lookup thành công có nghĩa `asCollector` chắc chắn tạo được adapter với mọi `arrayType` và `arrayLength` không? Vì sao?
10. Tại sao kiểm tra `handle.type()` trước khi gọi rất hữu ích trong hệ thống xây dựng chữ ký động?

## 15. Ghi nhớ

- **`asCollector(arrayType, arrayLength)`** thay một tham số mảng cuối của handle bằng đúng `arrayLength` tham số thành phần rồi gom chúng thành mảng khi gọi target.
- **`arrayLength = 0` hợp lệ:** target vẫn được gọi với mảng rỗng.
- **Số lượng là cố định trong kiểu của collector**; thiếu/thừa tham số tại `invokeExact` gây lỗi kiểu lời gọi.
- **Kiểu phần tử cũng phải đúng:** `String[].class` tạo các tham số `String`, `int[].class` tạo các tham số `int`.
- **`asCollector(collectArgPos, arrayType, arrayLength)`** cho phép gom ở vị trí tham số mảng cụ thể.
- **`asCollector`, `asSpreader` và `asVarargsCollector`** phục vụ ba nhu cầu khác nhau; chọn API theo hình dạng tham số mà caller và target cần.
- **Kiểm chứng bằng `base.type()` và `collector.type()`** giúp xác định rõ số tham số, thứ tự kiểu và nguyên nhân lỗi trước khi tối ưu hóa hệ thống.

