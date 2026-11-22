# Field.getInt(), getLong(), getDouble() và các chuyển đổi kiểu được phép

Khi đọc giá trị trường bằng Java Reflection, `java.lang.reflect.Field` cung cấp hai nhóm API: `get(Object)` trả về `Object`, còn các phương thức như `getInt(Object)`, `getLong(Object)`, `getDouble(Object)` trả về một **kiểu nguyên thủy cụ thể**. Những phương thức `getXxx` không đơn giản “ép” bất kỳ dữ liệu nào về kiểu `Xxx`: chúng chỉ chấp nhận trường có **kiểu nguyên thủy tương thích theo quy tắc chuyển đổi mở rộng** (*widening primitive conversion*).

Ví dụ, với một trường khai báo là `byte`, cả `getInt`, `getLong` và `getDouble` đều có thể đọc giá trị. Nhưng với trường `double`, gọi `getInt` sẽ ném `IllegalArgumentException`, kể cả khi giá trị `double` đang bằng `10.0`. Phép chuyển đổi được xét từ **kiểu khai báo của trường**, không phải dựa vào giá trị hiện tại có thể “vừa” trong kiểu đích hay không.

Bài học tập trung vào ba phương thức `getInt`, `getLong`, `getDouble`, đồng thời trình bày quy tắc chung để áp dụng đúng cho cả các primitive getter khác.

## 1. Field.getInt(), getLong(), getDouble() làm gì?

Một `Field` biểu diễn **một trường xác định trong lớp khai báo**, không phải một bản sao giá trị trường. Khi gọi getter, đối số `obj` chỉ ra đối tượng đang chứa giá trị cần đọc (hoặc `null` nếu là trường `static`).

| Phương thức | Kiểu Java trả về | Chấp nhận trường có kiểu khai báo |
| --- | --- | --- |
| `getInt(obj)` | `int` | `byte`, `short`, `char`, `int` |
| `getLong(obj)` | `long` | `byte`, `short`, `char`, `int`, `long` |
| `getDouble(obj)` | `double` | `byte`, `short`, `char`, `int`, `long`, `float`, `double` |

Tại mỗi dòng, trường có **cùng kiểu** với kiểu trả về cũng hợp lệ (chuyển đổi đồng nhất). Những kiểu còn lại hợp lệ vì tồn tại phép chuyển đổi **mở rộng primitive** từ kiểu của trường sang kiểu getter trả về.

Ví dụ các chuyển đổi hợp lệ:

- Trường `byte` chứa `12`: `field.getInt(obj)` trả `12` kiểu `int`; `getLong(obj)` trả `12L`; `getDouble(obj)` trả `12.0`.
- Trường `char` chứa ký tự `'A'`: `getInt(obj)` trả **65** (`char` là mã UTF-16 unsigned 16-bit, mở rộng lên `int` theo giá trị số).
- Trường `float` chứa `1.25f`: `getDouble(obj)` trả `1.25`.
- Trường `long`: `getDouble(obj)` được phép nhưng **có thể làm tròn, mất độ chính xác**.

Những ví dụ không hợp lệ:

- `getInt` trên `long`, `float` hoặc `double`: đây sẽ là **narrowing**, không được getter thực hiện.
- `getLong` trên `float` hoặc `double`: không có widening primitive conversion tương ứng.
- `getInt` trên `boolean`: `boolean` không chuyển đổi sang kiểu số theo widening.
- `getInt` trên `Integer`: `Integer` là **kiểu tham chiếu**, không phải trường primitive `int`. `getInt` không tự unbox đối tượng `Integer` đang được lưu trong trường.

## 2. Bảng chuyển đổi đầy đủ cho mọi primitive getter

Để không học thuộc từng hàm rời rạc, hãy ghi nhớ **kiểu nguồn là kiểu khai báo của trường**, **kiểu đích là kiểu trả về của getter**. Getter chỉ hỗ trợ identity hoặc một bước chuyển đổi widening primitive hợp lệ theo Java Language Specification.

| Getter | Kiểu trường được phép đọc |
| --- | --- |
| `getBoolean` | `boolean` |
| `getByte` | `byte` |
| `getShort` | `byte`, `short` |
| `getChar` | `char` |
| `getInt` | `byte`, `short`, `char`, `int` |
| `getLong` | `byte`, `short`, `char`, `int`, `long` |
| `getFloat` | `byte`, `short`, `char`, `int`, `long`, `float` |
| `getDouble` | `byte`, `short`, `char`, `int`, `long`, `float`, `double` |

Sơ đồ các đường chuyển đổi widening số thường gặp:

```text
byte  -> short -> int -> long -> float -> double
char  ---------> int -> long -> float -> double
                 (char không widening sang short hoặc byte)
```

Sơ đồ này biểu diễn các bước đi theo hướng mở rộng, bao gồm cả những bước có thể nhảy qua (chẳng hạn `byte -> double`). `short` **không** tự đổi thành `char`; `char` không đổi thành `short` vì miền giá trị khác nhau. `boolean` đứng riêng và chỉ có thể đọc qua `getBoolean`.

**Widening khác với casting/narrowing trong mã Java:** biểu thức Java có thể viết `(int) someDouble` với ép kiểu tường minh, nhưng `Field.getInt` không nhận một trường có kiểu `double`. Muốn đọc rồi ép kiểu có chủ đích, phải dùng getter đúng kiểu nguồn trước, sau đó thực hiện conversion ở tầng ứng dụng.

## 3. Ví dụ Java 17+ có thể biên dịch và chạy

Ví dụ dưới đây minh họa chuyển đổi widening thành công, hai trường hợp bị từ chối, cách đọc `static` field và trường hợp **widening vẫn mất độ chính xác số học**. Mọi field cần đọc được khai báo `public` trong lớp lồng để ví dụ tập trung vào quy tắc kiểu của getter, không vướng quyền truy cập.

Tạo tệp `FieldWideningDemo.java`:

```java
import java.lang.reflect.Field;

public class FieldWideningDemo {
    public static class Values {
        public byte small = 12;
        public char letter = 'A';
        public short portion = 32_000;
        public int count = 16_777_217; // 2^24 + 1
        public long huge = 9_007_199_254_740_993L; // 2^53 + 1
        public float fraction = 1.25f;
        public double price = 2.5;
        public Integer wrapper = 99;
        public boolean active = true;
        public static int staticCount = 7;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Values obj = new Values();

        Field small = Values.class.getDeclaredField("small");
        Field letter = Values.class.getDeclaredField("letter");
        Field portion = Values.class.getDeclaredField("portion");
        Field count = Values.class.getDeclaredField("count");
        Field huge = Values.class.getDeclaredField("huge");
        Field fraction = Values.class.getDeclaredField("fraction");
        Field price = Values.class.getDeclaredField("price");
        Field wrapper = Values.class.getDeclaredField("wrapper");
        Field active = Values.class.getDeclaredField("active");
        Field staticCount = Values.class.getDeclaredField("staticCount");

        System.out.println("byte -> int: " + small.getInt(obj));
        System.out.println("char -> long: " + letter.getLong(obj));
        System.out.println("short -> double: " + portion.getDouble(obj));
        System.out.println("float -> double: " + fraction.getDouble(obj));
        System.out.println("int -> float (rounded): " + (int) count.getFloat(obj));
        System.out.println("long -> double (rounded): " + (long) huge.getDouble(obj));
        System.out.println("static int -> long: " + staticCount.getLong(null));
        System.out.println("boolean -> boolean: " + active.getBoolean(obj));

        try {
            price.getInt(obj); // double -> int: không phải widening
        } catch (IllegalArgumentException ex) {
            System.out.println("double -> int: rejected");
        }

        try {
            wrapper.getInt(obj); // Integer là reference field
        } catch (IllegalArgumentException ex) {
            System.out.println("Integer -> int: rejected");
        }
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac FieldWideningDemo.java
java FieldWideningDemo
```

Kết quả:

```text
byte -> int: 12
char -> long: 65
short -> double: 32000.0
float -> double: 1.25
int -> float (rounded): 16777216
long -> double (rounded): 9007199254740992
static int -> long: 7
boolean -> boolean: true
double -> int: rejected
Integer -> int: rejected
```

Hai phép ép kiểu `(int) count.getFloat(obj)` và `(long) huge.getDouble(obj)` **chỉ dùng để in số nguyên sau khi giá trị đã bị làm tròn ở bước widening**, giúp dễ thấy chênh lệch. Chúng không phải conversion được `Field.getFloat` hay `Field.getDouble` tự thực hiện. Kết quả widening từ `16_777_217` thành `float` là `16_777_216.0f`; widening từ `9_007_199_254_740_993L` thành `double` là `9_007_199_254_740_992.0`.

Ở hai `try/catch`, chương trình minh họa **thất bại do kiểu nguồn không phù hợp**, không phải lỗi truy cập private field. `IllegalArgumentException` được bắt tại đúng vị trí để chương trình tiếp tục in những dòng còn lại.

### Đọc giá trị từ static field

Đối với `static` field, tham số receiver `obj` **được bỏ qua**; cách viết rõ ý định nhất là `staticCount.getLong(null)`. Với instance field, phải truyền instance hợp lệ, ví dụ `small.getInt(obj)`. Truyền `null` cho instance field sẽ gây `NullPointerException`, không phải “đọc giá trị mặc định”.

## 4. Widening được phép nhưng vẫn có thể mất precision

Từ “mở rộng” trong JLS không đồng nghĩa rằng mọi giá trị giữ nguyên toàn bộ chữ số có nghĩa. Cần phân biệt hai nhóm:

**Nhóm giữ chính xác giá trị khi widening:**

- `byte -> int/long/double`, `short -> int/long/double`, `char -> int/long/double`;
- `int -> long` và `int -> double`;
- `float -> double` giữ chính xác giá trị số *đã được biểu diễn bởi float* (không khôi phục dữ liệu có thể mất từ lúc tạo float).

**Nhóm có thể bị làm tròn:**

- `int -> float`;
- `long -> float`;
- `long -> double`.

Ví dụ, kiểu `int` có 32 bit, trong khi `float` thường có độ chính xác 24 bit nhị phân của significand. Vì vậy số nguyên `16_777_217 = 2^24 + 1` không thể được biểu diễn chính xác bằng `float`. Tương tự, `double` có 53 bit độ chính xác nhị phân, nên `2^53 + 1` không biểu diễn được chính xác dưới dạng `double`.

Các phép chuyển đổi này vẫn **hợp lệ theo API** và không ném lỗi: chương trình nhận kết quả đã làm tròn. Đây là điểm đặc biệt quan trọng khi xử lý mã định danh số lớn, timestamp có độ phân giải cao, giá trị tiền hoặc các phép so sánh đòi hỏi tuyệt đối chính xác. Với tài chính, nên lựa chọn kiểu dữ liệu và mô hình tính toán thích hợp từ đầu, thay vì dựa vào `float`/`double` để giữ nguyên mọi chữ số thập phân.

Một hiểu nhầm khác là “đọc `float` bằng `getDouble` sẽ làm phép tính ban đầu chính xác hơn”. Thực tế, nó chỉ biểu diễn **đúng giá trị float hiện có** bằng `double`; nếu float đã làm tròn khi được gán, việc đọc sẽ không phục hồi dữ liệu trước đó.

## 5. Primitive getter khác Field.get(Object) như thế nào?

`Field.get(Object)` luôn có kiểu trả về khai báo là `Object`:

- Nếu trường khai báo kiểu primitive, giá trị được **boxing** thành đối tượng wrapper phù hợp (`int -> Integer`, `long -> Long`, `double -> Double`...).
- Nếu trường khai báo kiểu tham chiếu, `get(obj)` trả về chính reference hiện có (có thể là `null`).
- `get(obj)` không tự thay đổi một `long` thành `double` theo kiểu getter đích mà chương trình mong muốn.

Ví dụ (đoạn mã minh họa, giả định `count`, `obj` và `wrapper` là các biến `Field`/`Values` đã khai báo trong ví dụ trên):

```java
Object boxedPrimitive = count.get(obj);  // Integer(16777217)
Object referenced = wrapper.get(obj);    // Integer(99)
int fromReference = ((Integer) referenced).intValue();
```

Ở đây `count` mô tả một trường primitive `int`, còn `wrapper` mô tả một trường reference `Integer`. Cả hai đều cho một `Integer` khi gọi `get`, nhưng lý do là khác nhau: primitive được boxing, còn reference đã lưu sẵn đối tượng `Integer`.

Chính vì vậy, không thể nhìn thấy `get` trả `Integer` rồi suy luận `wrapper.getInt(obj)` cũng sẽ hợp lệ. **Primitive getter kiểm tra kiểu khai báo của field**, không unbox tự động từ một field wrapper. Muốn xử lý nhiều trường có kiểu reference `Number`, trước tiên hãy đọc bằng `get(obj)`, kiểm tra kiểu/null, rồi chọn cách chuyển đổi ở ứng dụng — ý thức rằng `Number.intValue()` có thể thu hẹp, mất phần lẻ hoặc overflow theo kiểu nguồn.

Ví dụ chuyển đổi sau là **chủ động narrowing ngoài Reflection**, không phải hành vi của `getInt`:

```java
double value = price.getDouble(obj); // primitive double field
int narrowed = (int) value;           // Java cast tường minh
```

Không được dùng việc cast tường minh này để biện minh rằng `price.getInt(obj)` đáng lẽ phải thành công.

## 6. Lựa chọn getter theo metadata và yêu cầu dữ liệu

Với code phân tích/serialize nhiều field, nên kiểm tra kiểu khai báo bằng `field.getType()` và quyết định cách đọc dựa trên contract rõ ràng. Ví dụ:

```java
Class<?> type = field.getType();
if (type == int.class) {
    int value = field.getInt(receiver);
    // Xử lý giá trị int.
} else if (type == long.class) {
    long value = field.getLong(receiver);
    // Xử lý giá trị long.
} else if (type == double.class) {
    double value = field.getDouble(receiver);
    // Xử lý giá trị double.
} else {
    Object value = field.get(receiver);
    // Xử lý các kiểu khác, có thể gồm wrapper hoặc null.
}
```

Đoạn trên **không phải chương trình Java độc lập**: cần biến `field`, `receiver`, các khai báo cục bộ đúng phạm vi và xử lý/khai báo `IllegalAccessException`. Nó minh họa một cách dispatch rõ ràng theo kiểu. Nếu nghiệp vụ thực sự muốn mọi trường primitive số đều thành `double`, có thể chọn `getDouble` vì tất cả primitive kiểu số có đường widening tới `double`, nhưng vẫn cần chấp nhận nguy cơ precision loss với `long`.

Một API chỉ nhận kiểu đầu vào chính xác (ví dụ schema phân biệt `int` và `long`) nên kiểm tra `field.getType()` trước, thay vì gọi `getLong` lên mọi field rồi tưởng rằng mọi giá trị được đọc đều vốn là `long`.

**Không nhầm với `Field.setXxx`:** khi *ghi*, nguồn/đích của chuyển đổi đảo vai trò. `getDouble` đọc một `int` là hợp lệ, nhưng điều đó không chứng minh `setInt` sẽ nhận một trường khai báo `double` trong mọi ngữ cảnh khác mà không xét riêng hợp đồng API; hãy đọc tài liệu tương ứng của thao tác ghi. Các setter có quy tắc và hạn chế riêng, nhất là với field `final`.

## 7. Các ngoại lệ và điều kiện truy cập

Ngoài tương thích kiểu, một lần đọc field còn phải hợp lệ về đối tượng nhận, quyền truy cập và khởi tạo lớp:

| Tình huống | Hành vi cần dự kiến |
| --- | --- |
| Getter đích không nhận kiểu primitive của field (`getInt` cho `double`) | `IllegalArgumentException` |
| Primitive getter gọi trên field có kiểu reference (`Integer`, `String`, `Number`) | `IllegalArgumentException` |
| Instance field nhưng receiver `null` | `NullPointerException` |
| Instance field nhưng receiver sai kiểu đối tượng | `IllegalArgumentException` |
| Không có quyền đọc field qua Reflection | `IllegalAccessException` |
| Đọc static field kích hoạt khởi tạo lớp và việc khởi tạo thất bại | `ExceptionInInitializerError` |

Ví dụ `getDeclaredField("hidden")` có thể **tìm thấy** private field, nhưng không có nghĩa `getInt(obj)` được phép đọc. Cần tuân thủ Java language access rules và ranh giới module. Nếu đã có quyền bình thường thì không cần bật cờ suppress; nếu cần deep reflection, `canAccess(receiver)` và `trySetAccessible()` có thể giúp kiểm tra/yêu cầu quyền theo hợp đồng, nhưng không nên coi chúng là giải pháp mặc định để bỏ qua encapsulation.

`IllegalAccessException` là checked exception do các getter khai báo. `IllegalArgumentException` và `NullPointerException` là unchecked; việc `main` khai báo `throws ReflectiveOperationException` trong ví dụ không làm các lỗi dùng getter sai kiểu trở thành checked exception. Đây là lý do ví dụ bắt riêng hai `IllegalArgumentException` có chủ ý.

Khi getter đọc một `static` field, Java có thể khởi tạo declaring class nếu chưa khởi tạo. Nếu khởi tạo thất bại, lỗi liên quan tới quá trình khởi tạo, **không phải chuyển đổi từ `int` sang `long`**.

## 8. Sai lầm phổ biến khi làm việc với Field

**1. “Tên phương thức quyết định kiểu field phải khai báo.”** `getInt` không chỉ dành riêng cho field `int`, mà còn hợp lệ với `byte`, `short`, `char`. Đổi lại, nó không thể đọc trực tiếp field `long`, `float`, `double`.

**2. “Nếu giá trị nằm trong miền int thì getInt(doubleField) được phép.”** Sai; API xét **kiểu field**, không xét giá trị. Field `double` chứa `1.0` vẫn không hợp lệ với `getInt`.

**3. “getDouble không bao giờ mất dữ liệu.”** Sai; `long -> double` có thể mất độ chính xác dù conversion hợp lệ. Widening không nhất thiết là exact.

**4. “Wrapper Integer tương đương primitive int trong Reflection.”** Sai; `Field.getInt` không unbox trường reference. `Field.get` là lựa chọn để lấy wrapper, sau đó ứng dụng tự xử lý.

**5. “getLong có thể đọc float vì long 64 bit.”** Sai; quan hệ widening primitive dựa trên loại số và các quy tắc JLS, không chỉ độ rộng bit. `float -> long` là narrowing và không được `getLong` thực hiện.

**6. “char sang int sẽ trả ký tự như String.”** Sai; `getInt` trả giá trị số của UTF-16 code unit. Với `'A'`, kết quả là `65`, không phải chuỗi `"A"`.

**7. “Receiver luôn phải là instance.”** Sai với `static` field; truyền `null` là cách thể hiện rõ ràng. Nhưng instance field bắt buộc cần receiver hợp lệ.

**8. “Lỗi IllegalAccessException và IllegalArgumentException là giống nhau.”** Sai; một lỗi liên quan **quyền truy cập**, lỗi còn lại thường liên quan **kiểu getter hoặc receiver không phù hợp**. Xử lý đúng nguyên nhân thay vì thử `setAccessible(true)` để chữa mọi lỗi.

## 9. Tự kiểm tra

1. Field khai báo `byte` có thể dùng `getInt`, `getLong`, `getDouble` không? **Có**, vì có các đường widening tương ứng.
2. Field khai báo `char` có thể dùng `getShort` không? **Không**, `char -> short` không phải widening primitive conversion.
3. Field khai báo `float` có thể đọc bằng `getLong` không? **Không**; `float -> long` là narrowing.
4. Field khai báo `long` có thể đọc bằng `getDouble` không? **Có**, nhưng có thể mất precision.
5. Field `Integer` chứa giá trị `42` có đọc được qua `getInt` không? **Không**; đó là reference field. Dùng `get` rồi chuyển đổi có kiểm tra.
6. Field `double` chứa đúng `100.0` có đọc bằng `getInt` được không? **Không**; kiểu khai báo không tương thích.
7. Vì sao `getInt` có thể trả `65` khi field khai báo `char letter = 'A'`? **Vì `char -> int` là widening**, biểu diễn giá trị UTF-16 của `'A'` dưới dạng số.
8. Field `static int` có thể gọi `getLong(null)` không? **Có**: receiver bị bỏ qua cho static field và `int -> long` hợp lệ.

## 10. Tài liệu chính thức

- [Oracle Java SE 21 — `java.lang.reflect.Field`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html): hợp đồng của `get`, `getInt`, `getLong`, `getDouble`, các primitive getter khác, kiểu receiver và ngoại lệ.
- [Java Language Specification SE 21 — §5.1.2 Widening Primitive Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.2): danh sách chuyển đổi hợp lệ và các trường hợp có thể mất độ chính xác.

**Ghi nhớ:** Khi đọc bằng `Field.getInt/getLong/getDouble`, hãy đi từ **kiểu primitive khai báo của field** đến **kiểu trả về của getter** bằng identity hoặc widening. Không có narrowing tự động, không unbox wrapper field, và widening sang floating-point không phải lúc nào cũng giữ chính xác số ban đầu.