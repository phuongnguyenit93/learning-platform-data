# Field.setInt(), Field.setLong() và giới hạn widening trong Java Reflection

## 1. Học gì và vì sao cần hiểu quy tắc chuyển kiểu?

Với Java Reflection, đối tượng `java.lang.reflect.Field` đại diện cho một trường (field) đã được khai báo trong lớp hoặc interface. Ngoài `Field.set(Object, Object)` nhận giá trị dưới dạng đối tượng, Java cung cấp các phương thức chuyên cho kiểu nguyên thủy (primitive) như `setByte`, `setShort`, `setChar`, `setInt`, `setLong`, `setFloat` và `setDouble`.

Khi đã lấy được `Field`, ta có thể muốn ghi một giá trị số mà không cần đóng hộp tường minh thành `Integer` hoặc `Long`:

~~~java
Field field = Counter.class.getField("total"); // total là public long
field.setInt(counter, 42);                      // hợp lệ: int -> long
~~~

Đoạn trên chỉ minh họa khi đã có một đối tượng `counter` thuộc kiểu `Counter`. Ví dụ hoàn chỉnh, biên dịch được ở phần 5.

Điểm quan trọng: **kiểu của giá trị truyền vào phương thức `setXxx` không cần trùng hoàn toàn với kiểu khai báo của trường, nhưng chỉ được chuyển bằng phép đồng nhất kiểu (identity) hoặc mở rộng kiểu nguyên thủy (widening primitive conversion).** Reflection từ chối thu hẹp kiểu (narrowing), kể cả khi giá trị cụ thể nằm trong miền biểu diễn của kiểu đích.

Bài học này giải thích hai phương thức trọng tâm `setInt` và `setLong`, cách xét hướng chuyển đổi, sự khác biệt giữa `getXxx` và `setXxx`, tác động của precision và các lỗi thực tế.

## 2. Cơ chế của hai phương thức

Hai khai báo trong API `Field`:

~~~java
void setInt(Object obj, int i)
        throws IllegalArgumentException, IllegalAccessException;

void setLong(Object obj, long l)
        throws IllegalArgumentException, IllegalAccessException;
~~~

- `obj` là đối tượng chứa trường instance. Với trường `static`, có thể truyền `null` vì không có đối tượng nhận; với trường instance, truyền `null` gây `NullPointerException`.
- `i` là một **giá trị `int`**; `l` là một **giá trị `long`**. Loại tham số được cố định bởi chữ ký phương thức, không được suy từ trường đích.
- `Field` biết kiểu đích qua `getType()`; ở thời điểm ghi, Java kiểm tra giá trị đầu vào có thể được gán cho trường bằng phép đồng nhất hoặc widening primitive không.
- Nếu kiểu đích cho phép, giá trị được chuyển đổi rồi ghi vào trường. Nếu cần narrowing hoặc kiểu đích không tương thích, phương thức ném `IllegalArgumentException`. Nếu không có quyền ghi do kiểm tra truy cập hoặc tính `final`, có thể gặp `IllegalAccessException`.

Hình dung chiều dữ liệu:

~~~text
setInt(receiver, int)   -- identity / widening --> primitive field
setLong(receiver, long) -- identity / widening --> primitive field

Không có nhánh tự động narrowing để "ép vừa" trường đích.
~~~

**Phân biệt với ép kiểu trong Java:** phép ép tường minh như `(byte) 200` hoặc `(int) someLong` được thực hiện trước khi gọi setter, do lập trình viên yêu cầu. Bản thân `setInt`/`setLong` không thực hiện ép kiểu thu hẹp.

### Bảng tương thích quan trọng nhất

| Kiểu trường được khai báo | `setInt(obj, int)` | `setLong(obj, long)` | Lý do |
| --- | --- | --- | --- |
| `byte` | ❌ | ❌ | `int -> byte`, `long -> byte` đều là narrowing |
| `short` | ❌ | ❌ | Không chấp nhận `int/long -> short` |
| `char` | ❌ | ❌ | `int/long -> char` không phải widening |
| `int` | ✅ | ❌ | `int -> int` là identity; `long -> int` là narrowing |
| `long` | ✅ | ✅ | `int -> long` là widening; `long -> long` là identity |
| `float` | ✅ | ✅ | `int -> float` và `long -> float` là widening |
| `double` | ✅ | ✅ | `int -> double` và `long -> double` là widening |
| `boolean` | ❌ | ❌ | Không có chuyển đổi số sang `boolean` |
| `Integer`, `Long`, `Number` hoặc kiểu tham chiếu khác | ❌ | ❌ | Hai phương thức `setInt`/`setLong` dành cho trường primitive, không phải trường wrapper/reference |

Ở đây ✅ có nghĩa **hợp lệ về kiểu chuyển đổi** nếu đối tượng nhận và quyền truy cập cũng hợp lệ; nó không bảo đảm lời gọi luôn thành công khi trường `private`, `final` hoặc đối tượng không đúng kiểu.

Một cách ghi nhớ ngắn:

- `setInt` ghi được vào: **`int` → `long` → `float` → `double`**.
- `setLong` ghi được vào: **`long` → `float` → `double`**.
- **Không được đi ngược chiều về kiểu nhỏ hơn**, bất kể số cụ thể là `0`, `7` hay nằm trong khoảng của `byte`.

## 3. Widening là quy tắc kiểu, không phải so sánh kích thước giá trị

Theo quy tắc chuyển đổi kiểu nguyên thủy của Java, những hướng widening số thường gặp gồm:

~~~text
byte  -> short -> int -> long -> float -> double
          ^       ^       ^       ^        ^
char  ------------+-------+-------+--------+
~~~

Sơ đồ chỉ diễn đạt các hướng đi tiêu biểu; `char` **không** widening sang `byte` hay `short`. Bảng đầy đủ các hướng trực tiếp:

| Kiểu nguồn | Kiểu đích chấp nhận qua widening |
| --- | --- |
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |
| `double` | Không có kiểu primitive khác rộng hơn |
| `boolean` | Không widening sang kiểu số nào |

Mỗi kiểu cũng luôn cho phép phép chuyển đồng nhất sang chính nó. `setInt` bắt đầu từ nguồn `int`, còn `setLong` bắt đầu từ nguồn `long`; vì vậy chỉ cần xét hai hàng này cộng identity.

**Tại sao `setInt(fieldByte, 7)` lại lỗi dù số 7 vừa `byte`?** Java có quy tắc *thu hẹp hằng số tại thời điểm biên dịch* cho một số phép gán (ví dụ `byte b = 7;`). Đó là một quy tắc có điều kiện trong ngữ cảnh gán của mã nguồn, **không phải** quy tắc được `Field.setInt` áp dụng cho một `int` ở runtime. Reflection không nhìn vào giá trị rồi tự rút về `byte`.

Hai ví dụ độc lập:

~~~java
byte b = 7;                        // mã nguồn hợp lệ vì hằng int đặc biệt
Field f = Example.class.getField("b");  // Example có public byte b
f.setInt(example, 7);             // IllegalArgumentException
f.setByte(example, (byte) 7);     // đúng phương thức cho trường byte
~~~

Đoạn mã trên là minh họa, giả định `example` là instance hợp lệ của `Example`; chương trình đầy đủ ở phần 5.

Tương tự, `setLong(fieldInt, 5L)` bị từ chối, ngay cả khi `5L` nằm trong miền `int`. Nếu nghiệp vụ cho phép cắt giá trị, bạn phải đưa ra kiểm tra phạm vi và phép chuyển đổi tường minh trước; để `setInt` nhận `int` chỉ sau khi đã xác minh.

## 4. Gọi setter đúng cách và phân biệt với Field.set(Object, Object)

### 4.1. Chọn overload theo kiểu nguồn và kiểu đích

~~~java
Field f = Data.class.getField("total"); // public long total
Data d = new Data();

f.setInt(d, 123);                       // hợp lệ: int -> long
f.setLong(d, 123L);                     // hợp lệ: long -> long
~~~

Nếu trường là `public int count`:

~~~java
Field f = Data.class.getField("count"); // public int count
f.setInt(d, 123);                       // hợp lệ
f.setLong(d, 123L);                     // IllegalArgumentException
~~~

**Một bẫy cú pháp:** `f.setLong(d, 123)` vẫn biên dịch, vì trình biên dịch chuyển literal `123` từ `int` sang tham số `long` của phương thức. Khi `setLong` thực sự chạy, nó đang ghi **`long`** chứ không “ghi `int`”, nên một trường `int` vẫn bị từ chối. Tên setter quyết định kiểu nguồn mà runtime xét.

### 4.2. `set(Object, Object)` có thể unboxing rồi widening

Với một trường primitive, `Field.set(obj, value)` có thể **mở hộp (unboxing)** giá trị wrapper sau đó widening khi cần:

~~~java
Field total = Data.class.getField("total"); // long
total.set(d, Integer.valueOf(25));          // Integer -> int -> long: hợp lệ
~~~

Tương đương về kiểu giá trị với `total.setInt(d, 25)`. Ngược lại, với một trường reference:

~~~java
Field boxed = Data.class.getField("boxed"); // Integer boxed
boxed.set(d, Integer.valueOf(25));          // hợp lệ: đặt tham chiếu Integer
boxed.setInt(d, 25);                        // IllegalArgumentException
~~~

**Phân biệt hai khái niệm:** boxing `int -> Integer` thường xảy ra khi truyền đối số cho phương thức nhận `Object`, nhưng không có chuyện `Field.setInt` tự đổi một field khai báo `Integer` thành primitive. Setter chuyên biệt làm việc theo các quy tắc primitive field.

Khi chương trình nhận dữ liệu không biết kiểu trước, nên kiểm tra `field.getType()` và xử lý chuyển đổi một cách có chủ đích thay vì thử setter tùy ý rồi bắt lỗi.

### 4.3. Đừng đảo chiều quy tắc giữa get và set

- `field.setInt(obj, 7)`: nguồn là `int`, hỏi trường đích có nhận được `int` không.
- `field.getLong(obj)`: nguồn là **kiểu đang khai báo của trường**, hỏi giá trị lấy ra có widening sang `long` được không.

Do đó, `getLong` trên trường `int` hợp lệ, nhưng `setLong` trên trường `int` không hợp lệ. `getInt` trên trường `long` cũng bị từ chối vì `long -> int` là narrowing. Phần 5 cho ví dụ thực nghiệm về bất đối xứng này.

## 5. Chương trình Java 17+ hoàn chỉnh, chạy được

Chương trình này dùng **trường public, không final** để quan sát quy tắc chuyển kiểu mà không bị rối với quyền truy cập; có thêm ví dụ trường `static`, boxing và chiều của getter. Các dòng in lỗi được chuẩn hóa theo tên loại ngoại lệ để kết quả không phụ thuộc thông điệp lỗi của JDK.

Tạo tệp **`WideningFieldDemo.java`**:

~~~java
import java.lang.reflect.Field;

public class WideningFieldDemo {
    static class Metrics {
        public int count;
        public long total;
        public float roundedFloat;
        public double roundedDouble;
        public byte tiny;
        public char symbol;
        public Integer boxed;
        public static long shared;
    }

    @FunctionalInterface
    interface FieldAction {
        void run() throws IllegalAccessException;
    }

    static void attempt(String label, FieldAction action) {
        try {
            action.run();
            System.out.println(label + ": OK");
        } catch (IllegalArgumentException ex) {
            System.out.println(label + ": IllegalArgumentException");
        } catch (IllegalAccessException ex) {
            System.out.println(label + ": IllegalAccessException");
        }
    }

    public static void main(String[] args) throws Exception {
        Metrics m = new Metrics();
        Class<Metrics> type = Metrics.class;

        Field count = type.getField("count");
        Field total = type.getField("total");
        Field roundedFloat = type.getField("roundedFloat");
        Field roundedDouble = type.getField("roundedDouble");
        Field tiny = type.getField("tiny");
        Field symbol = type.getField("symbol");
        Field boxed = type.getField("boxed");
        Field shared = type.getField("shared");

        count.setInt(m, 7);
        total.setInt(m, 42);
        roundedFloat.setInt(m, 16_777_217);
        roundedDouble.setLong(m, 9_007_199_254_740_993L);
        shared.setLong(null, 99);

        System.out.println("count=" + m.count
                + ", total=" + m.total
                + ", shared=" + Metrics.shared);
        System.out.println("int->float rounded=" + (int) m.roundedFloat);
        System.out.println("long->double rounded=" + (long) m.roundedDouble);

        attempt("int->byte", () -> tiny.setInt(m, 7));
        attempt("int->char", () -> symbol.setInt(m, 65));
        attempt("long->int", () -> count.setLong(m, 8L));
        attempt("int->Integer", () -> boxed.setInt(m, 3));

        attempt("Integer->long via set",
                () -> total.set(m, Integer.valueOf(88)));
        System.out.println("total after set=" + m.total);

        System.out.println("getLong(int field)=" + count.getLong(m));
        attempt("getInt(long field)",
                () -> System.out.println(total.getInt(m)));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp (JDK 17 trở lên):

~~~bash
javac --release 17 WideningFieldDemo.java
java WideningFieldDemo
~~~

**Kết quả stdout đã xác minh trên JDK 21 khi biên dịch với `--release 17`:**

~~~text
count=7, total=42, shared=99
int->float rounded=16777216
long->double rounded=9007199254740992
int->byte: IllegalArgumentException
int->char: IllegalArgumentException
long->int: IllegalArgumentException
int->Integer: IllegalArgumentException
Integer->long via set: OK
total after set=88
getLong(int field)=7
getInt(long field): IllegalArgumentException
~~~

### Vì sao chương trình cho kết quả này?

1. `count.setInt(m, 7)` ghi nguyên giá trị vào trường `int`; `total.setInt(m, 42)` ghi vào `long` bằng widening. `shared.setLong(null, 99)` ghi vào trường `static long` mà không cần instance.
2. `roundedFloat.setInt(m, 16_777_217)` **được phép về kiểu** nhưng `float` không biểu diễn chính xác số này; khi ép lại sang `int` để quan sát, nhận `16_777_216`.
3. `roundedDouble.setLong(m, 9_007_199_254_740_993L)` **được phép về kiểu**, nhưng `double` làm tròn xuống giá trị biểu diễn gần nhất là `9_007_199_254_740_992`.
4. Bốn dòng lỗi tiếp theo chứng minh `int -> byte`, `int -> char`, `long -> int` đều không hợp lệ, và trường `Integer` không được nhận qua `setInt`.
5. `total.set(m, Integer.valueOf(88))` thành công vì `Field.set` mở hộp từ `Integer` thành `int` rồi widening sang `long`.
6. `count.getLong(m)` đọc từ `int` rồi widening sang `long`. Trái lại `total.getInt(m)` đòi hỏi `long -> int` nên thất bại.

Chạy ví dụ bằng classpath như lệnh trên sẽ tránh các rào cản truy cập giữa named module khác nhau; các trường được công khai để chỉ tập trung vào chuyển kiểu.

## 6. Widening không phải lời hứa giữ nguyên mọi chữ số

Một nhầm lẫn phổ biến là: “widening nghĩa là kiểu đích to hơn, vậy không bao giờ mất số liệu”. Thực tế, **các phép widening số nguyên sang số thực dấu phẩy động có thể mất độ chính xác (precision)**.

| Phép chuyển | Có hợp lệ? | Giá trị có được giữ chính xác cho mọi đầu vào? |
| --- | --- | --- |
| `int -> long` | Có | Có, mọi giá trị `int` biểu diễn được bằng `long` |
| `int -> float` | Có | Không, `float` chỉ có khoảng 24 bit precision ở phần định trị |
| `int -> double` | Có | Có, mọi `int` biểu diễn chính xác được bằng `double` |
| `long -> float` | Có | Không, có thể làm tròn |
| `long -> double` | Có | Không, `double` có khoảng 53 bit precision; các `long` lớn có thể làm tròn |

**Ví dụ mất precision:** `16_777_217` khác `16_777_216` một đơn vị, nhưng `float` ở vùng giá trị đó không chứa được số lẻ này chính xác. Tương tự, `9_007_199_254_740_993L` nằm vượt khoảng nguyên liên tiếp mà `double` có thể biểu diễn chính xác.

Widening không ném lỗi vì mất precision: phép chuyển được phép theo **loại kiểu**; kết quả số thực được làm tròn theo quy tắc Java. Nếu dữ liệu là số lượng chính xác, ID, tiền tệ hoặc số nguyên lớn, cần chọn kiểu lưu trữ phù hợp. Không chọn `float` hoặc `double` chỉ vì setter cho phép chuyển từ `int`/`long`.

Một lưu ý khác: ép kiểu tường minh trước khi gọi setter vẫn có thể gây mất giá trị. Ví dụ:

~~~java
long huge = 3_000_000_000L;
int narrowed = (int) huge; // ép kiểu thu hẹp có thể đổi giá trị
countField.setInt(instance, narrowed);
~~~

Lời gọi `setInt` ở dòng cuối không thể phục hồi thông tin đã mất tại phép ép `(int) huge`. Với nghiệp vụ cần chuyển an toàn, có thể kiểm tra trước bằng `Math.toIntExact(huge)`; phương thức này ném `ArithmeticException` nếu `long` nằm ngoài miền `int`.

## 7. Lỗi runtime: loại giá trị, quyền truy cập và đối tượng nhận

`IllegalArgumentException` từ setter thường báo **kiểu không tương thích**, nhưng không phải mọi lỗi reflection đều do widening.

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `IllegalArgumentException` với `setInt` hoặc `setLong` | Kiểu trường không cho phép identity/widening từ `int`/`long` | In `field.getType()`, dùng bảng phần 2 |
| `IllegalArgumentException` dù field là kiểu tương thích | `obj` không phải instance đúng của kiểu khai báo trường | So `field.getDeclaringClass()` và kiểu thực của receiver |
| `NullPointerException` | Truyền `null` cho field instance | Cung cấp instance, chỉ truyền `null` cho static |
| `IllegalAccessException` | Field không thể ghi do kiểm tra quyền truy cập, hoặc không có quyền ghi field `final` | Xem modifier, package, module và chính sách ghi |
| `NoSuchFieldException` | Tên field sai, hoặc `getField` chỉ tìm field public phù hợp | Xác minh tên; dùng `getDeclaredField` cho field khai báo trực tiếp không public |
| `ExceptionInInitializerError` | Việc thao tác field `static` kích hoạt khởi tạo lớp và khởi tạo thất bại | Xem nguyên nhân khởi tạo lớp |

Đối với **field private**, việc lấy được `Field` từ `getDeclaredField` không tự mở quyền ghi. Gọi `setAccessible(true)` hoặc `trySetAccessible()` chỉ có thể bỏ một số kiểm tra quyền khi JPMS cho phép; chúng **không** chuyển narrowing thành widening.

Đối với **field final**, ngoài kiểm tra quyền, API có giới hạn nghiêm ngặt khi ghi; một số dạng field final luôn không thể ghi thông qua cơ chế này, kể cả khi đã tắt kiểm tra truy cập. Đừng dùng reflection để sửa hằng số hay bất biến nội bộ. Trong chương trình minh họa, các field cần ghi được khai báo không final.

Với trường `static`, tham số `obj` bị bỏ qua để xác định instance, nhưng nên truyền `null` cho dễ đọc và tránh tạo đối tượng giả. Ghi static field có thể kích hoạt khởi tạo lớp nếu chưa khởi tạo.

## 8. Cách chọn API khi kiểu Field chỉ biết ở runtime

Nếu đang viết công cụ gán cấu hình, bộ ánh xạ dữ liệu hay kiểm thử reflection, nên phân biệt kiểu đích ngay từ đầu:

~~~java
Class<?> targetType = field.getType();

if (targetType == int.class) {
    field.setInt(receiver, intValue);
} else if (targetType == long.class) {
    field.setLong(receiver, longValue);
} else {
    // Xử lý các kiểu khác theo hợp đồng dữ liệu;
    // không tự coi mọi kiểu số là tương thích.
}
~~~

Đây là **mã minh họa**: giả sử đã có `field`, `receiver`, `intValue`, `longValue` và xử lý ngoại lệ thích hợp. Logic mẫu kiểm tra **kiểu đích chính xác**, phù hợp khi mỗi nguồn đã được kiểm chứng sẵn. Nếu muốn cho một nguồn `int` ghi vào `long`, `float`, `double`, hãy mở rộng rõ ràng các nhánh và quyết định chính sách precision; nếu muốn cho `long` ghi vào `int`, bắt buộc kiểm tra phạm vi và dùng phép chuyển tường minh.

Một quy trình an toàn:

1. **Xác định đích:** lấy `field.getType()`, `getModifiers()`, `getDeclaringClass()`; phân biệt primitive với wrapper và instance với static.
2. **Xác định nguồn:** một giá trị `int`, `long` hay một đối tượng wrapper thật sự? Với dữ liệu văn bản, parse dữ liệu theo hợp đồng thay vì đoán.
3. **Quyết định conversion:** chỉ dùng identity/widening được phép, đồng thời đánh giá có chấp nhận làm tròn khi sang `float`/`double` không.
4. **Kiểm tra quyền ghi:** field public, private hay final? Bên gọi có quyền phản chiếu phù hợp không? Hạn chế bỏ kiểm tra truy cập.
5. **Thực hiện và xử lý lỗi:** dùng setter đúng, ghi nhận lỗi kiểu và quyền truy cập riêng để xử lý được nguyên nhân.

Khi làm framework ánh xạ JSON, ORM hoặc mapper, chiến lược tương thích kiểu có thể rộng hơn cơ chế `Field.setInt`. Chẳng hạn converter nghiệp vụ có thể parse chuỗi `"42"` hoặc chuyển `long` sang `int` sau khi kiểm tra miền. Đó là **lớp chuyển đổi do ứng dụng tự viết**, không phải tính năng mà `setInt` tự cung cấp.

## 9. Bài tập thực hành và đáp án

**Bài 1.** Trường `public long total`. Dự đoán `setInt(obj, -5)` và `setLong(obj, -5L)` có được phép không.

**Đáp án:** Cả hai hợp lệ. `int -> long` là widening, `long -> long` là identity; giá trị `-5` được giữ nguyên.

**Bài 2.** Trường `public short age`. `setInt(obj, 12)` có thành công vì `12` nằm trong miền `short` không? Nếu không, nên làm gì?

**Đáp án:** Không, nó ném `IllegalArgumentException`. Dùng `setShort(obj, (short) 12)` sau khi bảo đảm miền giá trị của đầu vào, hoặc chuyển đổi có kiểm tra phạm vi ở tầng nghiệp vụ.

**Bài 3.** Trường `public int count`. Đoạn `setLong(obj, 3)` có hợp lệ không? Có gì khác `setInt(obj, 3)`?

**Đáp án:** `setLong(obj, 3)` vẫn biên dịch do literal được widening sang tham số `long`, nhưng setter ném `IllegalArgumentException` vì trường đích `int`. `setInt(obj, 3)` thành công.

**Bài 4.** Trường `public double amount`. Có thể gọi `setLong(obj, 9_007_199_254_740_993L)` không? Giá trị đọc lại có chắc chính xác không?

**Đáp án:** Gọi hợp lệ vì `long -> double` là widening, nhưng giá trị sẽ bị làm tròn trong ví dụ này; không bảo đảm giữ nguyên mọi bit số nguyên.

**Bài 5.** Trường `public Integer boxed`. Phương thức nào phù hợp giữa `setInt(obj, 42)` và `set(obj, Integer.valueOf(42))`?

**Đáp án:** Dùng `set(obj, Integer.valueOf(42))` để gán tham chiếu. `setInt` chuyên cho primitive field, nên không gán trực tiếp cho field khai báo `Integer`.

**Bài 6.** Trường `public int n`. Vì sao `getLong(obj)` thành công nhưng `setLong(obj, 5L)` thất bại?

**Đáp án:** Getter chuyển **kiểu trường `int` → kiểu trả về `long`** nên widening. Setter chuyển **kiểu tham số `long` → kiểu trường `int`** nên narrowing. Hướng conversion khác nhau.

**Bài 7.** Dùng `getDeclaredField("count")` lấy một field private kiểu `int`, rồi gọi `setLong(obj, 5L)` sau khi `trySetAccessible()` thành công. Có được ghi không?

**Đáp án:** Vẫn không, vì yêu cầu mở truy cập chỉ xử lý quyền kiểm tra của ngôn ngữ; `long -> int` vẫn là narrowing bị `Field.setLong` từ chối. Phải chọn kiểu đầu vào và phương thức thích hợp.

## 10. Ghi nhớ và tài liệu đối chiếu

**Quy tắc cốt lõi:** `Field.setInt` chỉ ghi vào field primitive `int`, `long`, `float`, `double`; `Field.setLong` chỉ ghi vào `long`, `float`, `double`. Runtime xét **hướng từ kiểu tham số setter sang kiểu field**, không xét giá trị có “vừa” kiểu nhỏ hơn hay không. Widening sang số thực đôi khi mất precision nhưng vẫn hợp lệ. Quyền truy cập, `final` và đối tượng nhận là các điều kiện bổ sung, độc lập với loại conversion.

Tài liệu chuẩn để tra cứu:

- [`java.lang.reflect.Field` — Java SE API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html): các phương thức `setInt`, `setLong`, `set(Object,Object)`, `getInt` và `getLong`.
- [Java Language Specification `5.1.2 — Widening Primitive Conversion](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-5.html#jls-5.1.2): các hướng widening và quy tắc precision.
