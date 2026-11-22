# `Field.get()` trả về wrapper khi field có kiểu primitive

## 1. Vấn đề: field là `int`, vì sao kết quả của `get()` là `Integer`?

Khi dùng Java Reflection để đọc một field, chữ ký API quan trọng nhất là:

~~~java
public Object get(Object obj) throws IllegalArgumentException, IllegalAccessException
~~~

`Field.get(Object)` có kiểu trả về **`Object`**, trong khi Java có tám kiểu primitive (`boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`). Primitive không phải đối tượng, nên không thể trực tiếp là giá trị trả về kiểu `Object`. Vì vậy, nếu field được khai báo là primitive, Java đọc giá trị primitive rồi **boxing** thành một đối tượng của wrapper tương ứng.

Ví dụ:

~~~java
class Counter {
    public int count = 42;
}

Counter counter = new Counter();
java.lang.reflect.Field field = Counter.class.getField("count");

Object result = field.get(counter);           // Integer chứa 42
System.out.println(field.getType());          // int
System.out.println(result.getClass());        // class java.lang.Integer
int count = (Integer) result;                 // cast + unboxing
~~~

Đoạn code trên là minh họa. `Field.getType()` trả về kiểu **khai báo trong class** (`int.class`), còn `result.getClass()` trả về class **của đối tượng được boxing** (`Integer.class`). Không có chuyện field ban đầu bị đổi từ `int` sang `Integer` trong đối tượng `Counter`.

Tư duy đúng là:

~~~text
Field khai báo int -> đọc giá trị int -> boxing thành Integer -> trả về Object
                                               |
                              getType() vẫn là int.class
~~~

Với field kiểu tham chiếu, `get()` trả về chính giá trị tham chiếu hiện tại (hoặc `null`), không tạo thêm wrapper chỉ vì kiểu trả về của phương thức là `Object`.

## 2. Bảng ánh xạ primitive và wrapper

| Kiểu khai báo của field | Đối tượng do `Field.get()` trả về khi field primitive |
| --- | --- |
| `boolean` | `Boolean` |
| `byte` | `Byte` |
| `short` | `Short` |
| `char` | `Character` |
| `int` | `Integer` |
| `long` | `Long` |
| `float` | `Float` |
| `double` | `Double` |

Đây là ánh xạ kiểu, không phải việc mọi lần gọi đều bắt buộc tạo đối tượng wrapper mới. Đừng dựa vào `==` giữa hai kết quả `Field.get()` để kiểm tra “có cùng giá trị primitive hay không”. Nếu cần so sánh dữ liệu, hãy unbox để dùng toán tử của primitive hoặc dùng phép so sánh giá trị phù hợp.

Một số điểm cần phân biệt:

- Field `int number` luôn lưu giá trị primitive `int`; `Field.get` biểu diễn kết quả bằng `Integer`. Primitive field không thể mang `null`.
- Field `Integer number` vốn là **kiểu tham chiếu**. `Field.get` trả chính tham chiếu `Integer` hoặc `null` đang có; bản thân field không phải primitive.
- Field `String name` cho ra `String`, không phải một “wrapper của String”.
- Field `int[] numbers` là **kiểu mảng tham chiếu**. `Field.get` trả về đối tượng `int[]`; nó không tự boxing từng phần tử thành `Integer[]`. Muốn lấy riêng một phần tử qua Reflection, xem `java.lang.reflect.Array.get`; với phần tử primitive, thao tác đó cũng biểu diễn giá trị bằng wrapper.

## 3. Ví dụ Java 17+ có thể biên dịch/chạy

Tạo file `FieldGetBoxingDemo.java`:

~~~java
import java.lang.reflect.Field;

public class FieldGetBoxingDemo {
    public static class Data {
        public int count = 42;
        public boolean enabled = true;
        public char letter = 'J';
        public long large = 3_000_000_000L;
        public Integer nullable = null;
        public String label = "Java";
        public static double factor = 1.5;
    }

    public static void main(String[] args) throws Exception {
        Data data = new Data();

        Field count = Data.class.getField("count");
        Object value = count.get(data);

        System.out.println("field type: " + count.getType().getName());
        System.out.println("result type: " + value.getClass().getSimpleName());
        System.out.println("result: " + value);
        System.out.println("unboxed + 1: " + ((Integer) value + 1));

        System.out.println("getInt: " + count.getInt(data));
        System.out.println("getLong widening: " + count.getLong(data));

        Object flag = Data.class.getField("enabled").get(data);
        System.out.println("boolean wrapper: "
                + flag.getClass().getSimpleName() + "=" + flag);

        Object letter = Data.class.getField("letter").get(data);
        System.out.println("char wrapper: "
                + letter.getClass().getSimpleName() + "=" + letter);

        Object large = Data.class.getField("large").get(data);
        System.out.println("long wrapper: "
                + large.getClass().getSimpleName() + "=" + large);

        Object staticValue = Data.class.getField("factor").get(null);
        System.out.println("static wrapper: "
                + staticValue.getClass().getSimpleName() + "=" + staticValue);

        System.out.println("nullable value: "
                + Data.class.getField("nullable").get(data));
        System.out.println("reference type: "
                + Data.class.getField("label").get(data)
                        .getClass().getSimpleName());

        try {
            Data.class.getField("large").getInt(data);
        } catch (IllegalArgumentException e) {
            System.out.println("getInt from long: "
                    + e.getClass().getSimpleName());
        }

        try {
            Data.class.getField("nullable").getInt(data);
        } catch (IllegalArgumentException e) {
            System.out.println("getInt from Integer: "
                    + e.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file:

~~~bash
javac --release 17 FieldGetBoxingDemo.java
java FieldGetBoxingDemo
~~~

Kết quả:

~~~text
field type: int
result type: Integer
result: 42
unboxed + 1: 43
getInt: 42
getLong widening: 42
boolean wrapper: Boolean=true
char wrapper: Character=J
long wrapper: Long=3000000000
static wrapper: Double=1.5
nullable value: null
reference type: String
getInt from long: IllegalArgumentException
getInt from Integer: IllegalArgumentException
~~~

### Giải thích kết quả

1. `count` được **khai báo** kiểu `int`, nên `count.getType().getName()` là `"int"`. Sau `count.get(data)`, biến `value` giữ tham chiếu đến `Integer` chứa 42, vì `get` bắt buộc trả `Object`.
2. `(Integer) value + 1` gồm phép cast sang `Integer`, sau đó **auto-unboxing** khi thực hiện phép cộng, kết quả là 43. Không nên cast trực tiếp `(int) value` trong code cần tương thích/tường minh vì kiểu tĩnh của `value` là `Object` và cần đảm bảo giá trị là wrapper phù hợp; cách dễ hiểu là `((Integer) value).intValue()` hoặc `int n = (Integer) value;`.
3. `getInt(data)` là API chuyên biệt trả về trực tiếp `int`. `getLong(data)` cũng hợp lệ đối với field `int` vì Java cho phép **widening primitive conversion** từ `int` sang `long`.
4. `enabled`, `letter`, `large`, `factor` được khai báo lần lượt `boolean`, `char`, `long`, `double`. `Field.get` cho về `Boolean`, `Character`, `Long`, `Double`; field static `factor` không cần một instance để đọc nên gọi `get(null)`.
5. `nullable` là field tham chiếu kiểu `Integer` có giá trị `null`; `get` trả `null`, không tự cung cấp số 0 hay sinh một wrapper. `label` là field tham chiếu kiểu `String`, kết quả thực sự là `String`.
6. `getInt` không chấp nhận đọc field `long` bằng cách thu hẹp kiểu (`long` → `int`), nên báo `IllegalArgumentException`. Nó cũng không đọc được field **khai báo `Integer`**: đây là kiểu tham chiếu, không phải field primitive `int`. Nếu cần wrapper field, dùng `get` rồi kiểm tra/null-check và ép kiểu thích hợp.

Ví dụ dùng các public field để tập trung vào quy tắc boxing. Với field private hoặc field thuộc module đóng, có thể cần xử lý quyền truy cập trước khi đọc; boxing không làm thay đổi access check.

## 4. Khác biệt giữa `get()` và các typed getter

`Field` cung cấp các getter trả về primitive cụ thể:

~~~java
boolean getBoolean(Object obj)
byte    getByte(Object obj)
short   getShort(Object obj)
char    getChar(Object obj)
int     getInt(Object obj)
long    getLong(Object obj)
float   getFloat(Object obj)
double  getDouble(Object obj)
~~~

Các method trên là API của `java.lang.reflect.Field`, không phải code mới cần tự cài đặt. Mỗi method nhận receiver tương tự `get(obj)`, nhưng **kiểu trả về là primitive**, nên phù hợp khi cần tính toán và muốn tránh API trả `Object`.

### Quy tắc chuyển đổi kiểu

- `get()` trả `Object`: field primitive được boxing thành **đúng wrapper tương ứng với kiểu của field**. Không tự chuyển field `int` thành `Long` chỉ vì caller muốn số `long`.
- `getInt()` đọc được một field nguyên thủy kiểu `byte`, `short`, `char` hoặc `int` thông qua phép mở rộng kiểu primitive (widening) đến `int`. Không đọc được field `long`, `float`, `double`, `boolean` hoặc field tham chiếu `Integer`.
- `getLong()` đọc được các field primitive `byte`, `short`, `char`, `int` hoặc `long`; ví dụ từ field `int` có thể mở rộng thành `long`.
- `getDouble()` có thể đọc các kiểu số primitive được phép widening đến `double` (`byte`, `short`, `char`, `int`, `long`, `float`, `double`).
- `getBoolean()` chỉ phù hợp với field có kiểu primitive `boolean`. `boolean` không widening sang số.
- `getByte()` chỉ nhận `byte`; `getChar()` chỉ nhận `char`. Các getter còn lại tuân theo widening primitive hợp lệ của Java.

Typed getter không thực hiện unboxing field kiểu tham chiếu. Một field khai báo `Integer` vẫn cần `Field.get()`; đối tượng trả về có thể là `null`. Đây là khác biệt thiết yếu giữa **chuyển đổi widening primitive** và **unboxing wrapper**.

Ví dụ dưới đây là mảnh code dùng lại `count` và `data` trong chương trình trên:

~~~java
int exact = count.getInt(data);     // 42, primitive int
long wider = count.getLong(data);   // 42L, int -> long
Object boxed = count.get(data);    // Integer, vì get trả Object
~~~

Không nên mặc định typed getter là “cách đọc nào cũng ép được” như cơ chế chuyển đổi của trình ánh xạ dữ liệu. Khi kiểu khai báo không phù hợp, nó ném `IllegalArgumentException` thay vì tự parse số hay thực hiện narrowing cast.

## 5. Kiểu khai báo và kiểu giá trị: cách kiểm tra đúng

Trong mã làm việc với nhiều field khác nhau, thường cần xét `Field.getType()` **trước** khi ép kiểu:

~~~java
Class<?> declared = count.getType();
if (declared == int.class) {
    int n = count.getInt(data);
    System.out.println(n);
}
~~~

Đây là mảnh code dùng lại biến `count` và `data` từ ví dụ. Với field primitive, `getType()` trả về `int.class`, `boolean.class`,… (các `Class` đại diện kiểu primitive). Với field kiểu wrapper, `getType()` là `Integer.class`, `Boolean.class`,… và `isPrimitive()` trả `false`. Có thể phân nhánh:

~~~java
Class<?> declared = field.getType();
if (declared.isPrimitive()) {
    // Dữ liệu trong field là primitive; get() sẽ boxing khi trả Object.
} else {
    // Dữ liệu field là tham chiếu, có thể null.
}
~~~

Đây cũng là mảnh minh họa; `field` đại diện một `Field` đã được tra cứu. Không gọi `result.getClass()` trước khi kiểm tra `result != null`: với field tham chiếu chứa `null`, bạn sẽ gặp `NullPointerException`. Ngược lại, field primitive luôn có một giá trị primitive (kể cả giá trị mặc định 0, `false`, `'\0'`), nên kết quả `Field.get` của một field primitive đã đọc thành công không phải `null`.

Một lỗi khác là dựa vào `value.getClass() == Integer.class` để suy rằng **field khai báo `int`**. Điều đó không chính xác: kết quả `Field.get` từ một field `int` và một field `Integer` không-null đều có thể là `Integer`. Muốn phân biệt, phải dùng **`Field.getType()`**.

## 6. Những yếu tố dễ làm việc đọc field thất bại

Cơ chế boxing chỉ diễn ra sau khi đọc field thành công. Các lỗi khi tìm/đọc field là vấn đề riêng:

| Tình huống | Hành vi cần lưu ý |
| --- | --- |
| `getField("x")` nhưng field không public/không nằm trong public lookup | `NoSuchFieldException`; thử `getDeclaredField` trên đúng declaring class nếu thực sự cần member không-public |
| `get()` field private khi caller không có quyền | `IllegalAccessException`; `getDeclaredField` không tự bật quyền |
| Đọc instance field với `null` receiver | `NullPointerException`; phải có object đích |
| Truyền object không thuộc kiểu khai báo field | `IllegalArgumentException` |
| Đọc static field bằng `get(null)` | Hợp lệ; receiver bị bỏ qua cho static field, vẫn phải đáp ứng quyền truy cập |
| Gọi typed getter `getInt` trên field `Integer`/`long` | `IllegalArgumentException` do kiểu khai báo không phù hợp |
| Truy cập private field xuyên named module bằng deep reflection | `trySetAccessible()` có thể trả `false`; `setAccessible(true)` có thể ném `InaccessibleObjectException` |
| `get()` trả `null`, sau đó gọi `getClass()`/unbox | `NullPointerException` của code xử lý `null`, không phải “boxing primitive thành null” |

Với named module, cần phân biệt `exports` cho API public và `opens` cho deep reflection vào package khi module khác yêu cầu. Không mặc định `setAccessible(true)` thành công. Nếu một ứng dụng phụ thuộc vào field private, hãy ưu tiên API truy cập chính thức khi có thể.

## 7. Hiệu năng, boxing và lựa chọn API

Nếu mục đích là xử lý một số lượng lớn field primitive trên đường thực thi nóng, `getInt`/`getLong` có kiểu trả về primitive và tránh việc **API bắt buộc** trả `Object`, nên là lựa chọn tự nhiên khi biết trước kiểu. Tuy nhiên Reflection nói chung có chi phí runtime, và JVM có thể tối ưu boxing/cấp phát tùy trường hợp; không nên kết luận `Field.get` **luôn** cấp phát một wrapper mới hay một typed getter **luôn** nhanh hơn đáng kể khi chưa đo đạc.

Các cách chọn thường hợp lý:

1. Biết rõ field `int` và cần tính toán: dùng `getInt(receiver)`, có xử lý `IllegalAccessException`.
2. Cần một API chung đọc nhiều kiểu field: dùng `get(receiver)`; khi field primitive, kết quả sẽ được boxing, và bạn xử lý qua `Object`/wrapper.
3. Field thực sự khai báo wrapper `Integer`: dùng `get(receiver)`, xét trường hợp `null`; không dùng `getInt`.
4. Cần phân loại kiểu một cách đáng tin: dùng `field.getType()`, xét `isPrimitive()` và các class nguyên thủy cụ thể; đừng chỉ dựa vào class của object kết quả.

**Tự kiểm tra:**

- Một field `double price = 1.25;` được đọc qua `Field.get` trả đối tượng kiểu gì? → `Double`.
- Một field `Integer price = null;` được đọc qua `Field.get` trả gì? → `null`; không boxing giá trị mới.
- `Field.getType()` của field `int count` là `Integer.class` hay `int.class`? → `int.class`.
- `getLong` đọc field `int` được không? → Được, nhờ widening primitive `int` sang `long`.
- `getInt` đọc field khai báo `Integer` được không? → Không, vì typed getter không unbox field tham chiếu.
- `Field.get` đọc field `int[]` có trả `Integer[]` không? → Không, nó trả tham chiếu đến `int[]`; mảng primitive không tự đổi thành mảng wrapper.

Điểm cần nhớ là **Reflection giữ nguyên kiểu khai báo của field**. Chỉ giá trị trả về qua `Field.get(Object)` cần được biểu diễn dưới dạng `Object`, nên primitive mới được boxing thành wrapper; những thao tác typed getter và kiểm tra `getType()` giúp giữ ranh giới này rõ ràng.
