# Primitive và wrapper không có quan hệ kế thừa thay cho boxing

Khi làm việc với Java Reflection, ta thường gặp hai kiểu biểu diễn có vẻ liên quan: kiểu nguyên thủy như `int` và lớp bao như `Integer`. Cả hai đều có đối tượng `Class<?>` tương ứng, nhưng **boxing/unboxing là quy tắc chuyển đổi giá trị của ngôn ngữ Java, không phải quan hệ kế thừa giữa hai kiểu**. Vì vậy, API kiểm tra quan hệ kiểu và API gọi phương thức bằng reflection có thể cho kết quả khác nhau mà vẫn hoàn toàn nhất quán.

Bài này tập trung vào việc đọc chính xác `Class`, `isAssignableFrom`, `isInstance`, tra cứu chữ ký phương thức, truyền đối số qua `Method.invoke` và truy cập `Field`.

## 1. Phân biệt primitive, wrapper và boxing

Java có các kiểu primitive như `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`. Mỗi primitive có một lớp wrapper tương ứng: `Boolean`, `Byte`, `Short`, `Character`, `Integer`, `Long`, `Float`, `Double`.

| Góc nhìn | `int` | `Integer` |
| --- | --- | --- |
| Loại kiểu | Primitive | Reference type (class) |
| Giá trị | Giá trị số nguyên trực tiếp | Tham chiếu đến đối tượng chứa số nguyên |
| `Class` token | `int.class` hay `Integer.TYPE` | `Integer.class` |
| `isPrimitive()` | `true` | `false` |
| Kế thừa từ `Number`/`Object` | Không | `Integer` kế thừa `Number`, và `Number` kế thừa `Object` |
| Có thể nhận `null` | Không | Có |
| `instanceof` | Không dùng trực tiếp trên giá trị primitive | Có thể dùng trên đối tượng wrapper |

Ví dụ Java biên dịch tự động chèn chuyển đổi thích hợp:

```java
int primitive = 7;
Integer boxed = primitive;   // boxing: int -> Integer
int restored = boxed;       // unboxing: Integer -> int
Number number = primitive;  // boxing int -> Integer, rồi widening reference -> Number
Object object = primitive;  // boxing int -> Integer, rồi widening reference -> Object
```

`Integer` không `extends int`; primitive không phải lớp trong cây kế thừa. **Gán được nhờ chuyển đổi** không có nghĩa **có quan hệ subtype**.

Cũng cần tách hai khái niệm khác: `int` có thể *widen* thành `long` trong ngữ cảnh chuyển đổi số, nhưng `long` không phải lớp cha của `int`. Và không có quy tắc tổng quát tự động chuyển `Integer` thành `Long` chỉ vì giá trị số có thể đổi từ `int` sang `long`.

## 2. Class token biểu diễn danh tính kiểu, không thực hiện boxing

`int.class` và `Integer.class` là hai đối tượng `Class` khác nhau. `Integer.TYPE` chỉ là hằng tham chiếu tới `int.class`, **không** phải `Integer.class`:

```java
System.out.println(int.class == Integer.TYPE);       // true
System.out.println(int.class == Integer.class);      // false
System.out.println(int.class.isPrimitive());         // true
System.out.println(Integer.class.isPrimitive());     // false
```

Bản thân `Class` có thể mô tả primitive dù primitive không phải đối tượng thuộc hệ kế thừa `Object`. Chẳng hạn `int.class.getSuperclass()` trả về `null`; `Integer.class.getSuperclass()` trả về `Number.class`.

`value.getClass()` luôn được gọi trên một **đối tượng**. Với `int n = 7;`, biểu thức `((Object) n).getClass()` trả về `Integer.class` vì compiler đã boxing `n` khi ép sang `Object`. Không thể suy ra từ đó rằng đối tượng lúc chạy có lớp `int.class`.

## 3. `isAssignableFrom` kiểm tra quan hệ kiểu, không mô phỏng phép gán có chuyển đổi

Đọc biểu thức `Destination.class.isAssignableFrom(Source.class)` là: một giá trị có **kiểu Source** có thể được coi là **kiểu Destination** bằng quan hệ cùng kiểu hoặc quan hệ mở rộng kiểu thích hợp hay không? Với reference types, kiểm tra này xét kế thừa/lớp và interface. Với primitive, chỉ chính kiểu primitive đó mới tương thích theo phép kiểm tra này. API **không** tính boxing, unboxing hay widening primitive như `int → long`.

| Biểu thức | Kết quả | Lý do |
| --- | --- | --- |
| `Integer.class.isAssignableFrom(int.class)` | `false` | `int` không là subtype của `Integer` |
| `int.class.isAssignableFrom(Integer.class)` | `false` | `Integer` không là subtype của `int` |
| `Object.class.isAssignableFrom(int.class)` | `false` | Primitive không kế thừa `Object` |
| `Object.class.isAssignableFrom(Integer.class)` | `true` | `Integer` là reference subtype của `Object` |
| `Number.class.isAssignableFrom(Integer.class)` | `true` | `Integer extends Number` |
| `long.class.isAssignableFrom(int.class)` | `false` | Primitive widening không phải assignability theo API |
| `int.class.isAssignableFrom(int.class)` | `true` | Cùng một kiểu |

Lưu ý: mô tả «có thể gán» ở tên API dễ gây hiểu nhầm nếu suy diễn rằng nó thực hiện mọi conversion mà cú pháp gán Java chấp nhận. Ví dụ `Integer boxed = 7;` hợp lệ nhờ boxing, nhưng `Integer.class.isAssignableFrom(int.class)` vẫn `false`.

## 4. `isInstance` kiểm tra đối tượng lúc chạy

`someClass.isInstance(value)` kiểm tra xem `value` là một instance của reference type được đại diện hay không; `null` luôn cho `false`. `int.class.isInstance(...)` luôn `false` vì không có đối tượng Java nào thuộc lớp runtime `int`:

```java
Integer value = Integer.valueOf(7);

System.out.println(Integer.class.isInstance(value)); // true
System.out.println(Number.class.isInstance(value));  // true
System.out.println(Object.class.isInstance(value));  // true
System.out.println(int.class.isInstance(value));     // false
System.out.println(Integer.class.isInstance(null));  // false
```

Ở đây `value` là đối tượng `Integer`. Khi viết `int.class.isInstance(7)`, số `7` được boxing trước để đưa vào tham số kiểu `Object` của `isInstance`, nhưng token `int.class` vẫn không đại diện cho kiểu runtime của đối tượng đó.

**Quy tắc chọn API:** `isPrimitive()` để nhận diện loại `Class`; `isAssignableFrom` để kiểm tra quan hệ kiểu; `isInstance` để kiểm tra một đối tượng thực tại runtime. Không API nào thay thế đầy đủ bộ quy tắc conversion của compiler.

## 5. Tra cứu phương thức bằng chữ ký chính xác; gọi phương thức có chuyển đổi đối số

Đây là điểm dễ nhầm nhất của Reflection: **tra cứu phương thức** và **gọi phương thức** là hai bước khác nhau.

Giả sử lớp có `void consume(int n)`:

- `getMethod("consume", int.class)` tìm đúng chữ ký và thành công; `getMethod("consume", Integer.class)` không tìm được chữ ký đó và ném `NoSuchMethodException`.
- Sau khi có `Method` tương ứng với `int`, `method.invoke(target, Integer.valueOf(5))` có thể chạy: đối số của `Method.invoke` đi qua `Object...` và khi gọi phương thức đích, reflection unbox `Integer` thành `int`.
- Nếu phương thức đích nhận `long`, một đối số `Integer` có thể được **unbox sang `int` rồi widening sang `long`**.
- Reflection không tự chọn overload từ đối tượng đối số: bạn phải tra cứu đúng `int.class`, `long.class` hoặc `Integer.class` theo phương thức muốn gọi.

Các quy tắc trên không biến `Integer` thành subtype của `int` hoặc `long`; đây là **invocation conversion tại thời điểm gọi**. Một `Long` truyền cho tham số `int` bị từ chối vì cần narrowing; `Integer` truyền cho tham số `Long` cũng bị từ chối vì không có conversion wrapper-sang-wrapper như thế. Với tham số primitive, `null` không unbox được và bị từ chối.

### Ví dụ Java 17+ chạy độc lập

Lưu đoạn sau vào `BoxingAndReflectionDemo.java`. Chương trình phân biệt rõ kiểm tra `Class`, tìm chữ ký, `Method.invoke`, và đọc/ghi field primitive.

```java
public class BoxingAndReflectionDemo {
    public static class Target {
        public int count = 3;

        public void takeInt(int x) {
            System.out.println("takeInt=" + x);
        }

        public void takeLong(long x) {
            System.out.println("takeLong=" + x);
        }

        public void takeInteger(Integer x) {
            System.out.println("takeInteger=" + x);
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("int.class.isPrimitive(): "
                + int.class.isPrimitive());
        System.out.println("Integer.class.isPrimitive(): "
                + Integer.class.isPrimitive());
        System.out.println("Integer.class.isAssignableFrom(int.class): "
                + Integer.class.isAssignableFrom(int.class));
        System.out.println("int.class.isAssignableFrom(Integer.class): "
                + int.class.isAssignableFrom(Integer.class));
        System.out.println("Number.class.isAssignableFrom(Integer.class): "
                + Number.class.isAssignableFrom(Integer.class));
        System.out.println("Object.class.isAssignableFrom(int.class): "
                + Object.class.isAssignableFrom(int.class));
        System.out.println("int.class.isInstance(Integer.valueOf(1)): "
                + int.class.isInstance(Integer.valueOf(1)));
        System.out.println("Integer.class.isInstance(Integer.valueOf(1)): "
                + Integer.class.isInstance(Integer.valueOf(1)));

        try {
            Target.class.getMethod("takeInt", Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("getMethod(Integer.class): NOT_FOUND");
        }

        Target target = new Target();
        Target.class.getMethod("takeInt", int.class)
                .invoke(target, Integer.valueOf(5));
        Target.class.getMethod("takeLong", long.class)
                .invoke(target, Integer.valueOf(8));

        try {
            Target.class.getMethod("takeInt", int.class)
                    .invoke(target, Long.valueOf(5));
        } catch (IllegalArgumentException e) {
            System.out.println("Long -> int: REJECTED");
        }

        java.lang.reflect.Field field = Target.class.getField("count");
        Object read = field.get(target);
        System.out.println("field.get returns: "
                + read.getClass().getSimpleName() + "=" + read);

        field.set(target, Integer.valueOf(9));
        System.out.println("field int after set: " + target.count);
        try {
            field.set(target, null);
        } catch (IllegalArgumentException e) {
            System.out.println("null -> primitive: REJECTED");
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac BoxingAndReflectionDemo.java
java BoxingAndReflectionDemo
```

Output:

```text
int.class.isPrimitive(): true
Integer.class.isPrimitive(): false
Integer.class.isAssignableFrom(int.class): false
int.class.isAssignableFrom(Integer.class): false
Number.class.isAssignableFrom(Integer.class): true
Object.class.isAssignableFrom(int.class): false
int.class.isInstance(Integer.valueOf(1)): false
Integer.class.isInstance(Integer.valueOf(1)): true
getMethod(Integer.class): NOT_FOUND
takeInt=5
takeLong=8
Long -> int: REJECTED
field.get returns: Integer=3
field int after set: 9
null -> primitive: REJECTED
```

Giải thích ba kết quả quan trọng:

1. `getMethod("takeInt", Integer.class)` thất bại vì khai báo dùng `int`; chữ ký Java không «tương đương» chỉ vì compiler có boxing.
2. `takeInt=5` và `takeLong=8` xảy ra vì API gọi reflection nhận giá trị wrapper rồi áp dụng **unboxing**, kết hợp **widening primitive** khi hợp lệ. Đây không phải kết quả của `isAssignableFrom`.
3. `Field.get(target)` trả về `Object`; khi đọc field `int count`, reflection tạo/đưa ra wrapper `Integer`. Ngược lại, `Field.set(target, Integer.valueOf(9))` unbox để ghi field `int`. `null` không thể gán cho primitive.

## 6. Bảng chuyển đổi đối số cần nhớ

Bảng này mô tả **đối số truyền tới tham số phương thức đích bằng `Method.invoke`**, không phải kết quả `Class.isAssignableFrom` và không phải quy tắc tra cứu `getMethod`.

| Kiểu đối tượng đối số thực tế | Tham số khai báo | Khi gọi bằng reflection | Lý do |
| --- | --- | --- | --- |
| `Integer` | `int` | Chấp nhận | Unboxing |
| `Integer` | `long` | Chấp nhận | Unboxing rồi widening primitive |
| `Byte` | `double` | Chấp nhận | Unboxing rồi widening primitive |
| `Long` | `int` | Từ chối | Không implicit narrowing primitive |
| `Integer` | `Long` | Từ chối | Không có conversion ngầm từ wrapper này sang wrapper kia |
| `Integer` | `Number` hoặc `Object` | Chấp nhận | Widening reference |
| `null` | `int` | Từ chối | Primitive không nhận `null` |
| `null` | `Integer` | Chấp nhận | Reference type nhận `null` |

Vì khai báo `Method.invoke(Object obj, Object... args)` nhận đối số qua `Object...`, nếu ở mã gọi bạn viết `invoke(target, 5)`, compiler Java trước hết boxing `5` thành `Integer` để đưa vào mảng `Object[]`. Reflection sau đó có thể unbox lại `Integer` cho tham số đích `int`. **Hai thời điểm chuyển đổi khác nhau**, không phải hai kiểu có quan hệ kế thừa.

Nếu truyền sai kiểu ở tầng reflection, thường nhận `IllegalArgumentException`. Nếu *mã bên trong phương thức đích* tự ném exception thì `Method.invoke` bọc nguyên nhân trong `InvocationTargetException`; đừng nhầm hai trường hợp khi chẩn đoán lỗi.

## 7. Field và mảng primitive cũng theo nguyên tắc tương tự

Với `Field`, kiểu khai báo được mô tả chính xác bằng `field.getType()`. Nếu field khai báo `int`, kết quả là `int.class`, **không** phải `Integer.class`:

```java
java.lang.reflect.Field field =
        BoxingAndReflectionDemo.Target.class.getField("count");
System.out.println(field.getType() == int.class); // true
```

`Field.get(Object)` luôn trả về `Object`, nên giá trị primitive được boxing trong kết quả. Khi ghi bằng `Field.set(Object, Object)`, API có thể unbox wrapper và thực hiện widening primitive được phép; `Field.setInt`, `Field.getInt` và các getter/setter chuyên biệt cho primitive là lựa chọn khi muốn biểu đạt loại dữ liệu rõ hơn.

Mảng `int[]` và `Integer[]` vẫn khác kiểu:

```java
System.out.println(int[].class.isAssignableFrom(Integer[].class)); // false
System.out.println(Integer[].class.isAssignableFrom(int[].class)); // false
```

Phản chiếu `java.lang.reflect.Array.get(intArray, index)` trả về `Object` nên phần tử `int` được boxing. Điều đó không làm `int[]` kế thừa `Integer[]` hoặc ngược lại.

## 8. Những lỗi thường gặp khi thiết kế code Reflection

**Lỗi 1 — Dùng `isAssignableFrom` để kiểm tra xem một đối số có thể truyền tới primitive hay không.** Ví dụ `long.class.isAssignableFrom(Integer.class)` là `false`, nhưng một `Integer` có thể được unbox rồi widen để truyền cho tham số `long` khi gọi bằng reflection. Muốn tự xây dựng bộ kiểm tra đối số, phải xét rõ `null`, reference subtype, wrapper tương ứng và bảng widening primitive thay vì chỉ dùng một phép `isAssignableFrom`.

**Lỗi 2 — Thay `int.class` bằng `Integer.class` khi tìm `Method`/`Constructor`.** Các API `getMethod`, `getDeclaredMethod` và tra cứu constructor dùng kiểu tham số khai báo cụ thể; sự tồn tại của boxing không đổi chữ ký. Ví dụ `void save(int id)` phải được tìm với `int.class`. Nếu có cả `save(int)` và `save(Integer)`, đó là **hai overload riêng biệt**.

**Lỗi 3 — Tưởng `getClass()` trên giá trị đã boxing cho biết kiểu primitive gốc.** `Object obj = 10;` chứa tham chiếu tới một `Integer`, nên `obj.getClass() == Integer.class`. Thông tin «ban đầu từng là `int`» không còn được giữ trong runtime class của đối tượng.

**Lỗi 4 — Gộp numeric widening với inheritance.** `int → long` là phép chuyển đổi primitive, không làm `int.class.isAssignableFrom(long.class)` hoặc chiều ngược lại thành `true`. Tương tự, widening `int → long` không tạo ra phép `Integer → Long`.

**Lỗi 5 — Bỏ qua `null` và exception.** Unboxing biến `null` thành lỗi; qua reflection, `null` tới primitive bị từ chối ở lớp gọi. Đừng tự động bắt mọi exception rồi coi như «không tương thích», vì lỗi do thân phương thức ném ra có ý nghĩa khác lỗi truyền đối số.

## 9. Quy trình xử lý khi viết thư viện Reflection

Khi nhìn thấy một giá trị và một kiểu đích, hãy phân biệt câu hỏi trước khi chọn API:

1. **Đang phân tích khai báo?** Dùng `getParameterTypes()`, `getReturnType()`, `Field.getType()` và lưu nguyên token primitive như `int.class`.
2. **Đang kiểm tra quan hệ kiểu thuần túy?** Dùng `isAssignableFrom` cho đúng ngữ nghĩa subtype/identity; đừng thêm boxing vào kết luận.
3. **Đang kiểm tra một instance hiện có?** Dùng `isInstance` cho reference object, xử lý `null` riêng.
4. **Đang truyền giá trị vào lời gọi?** Xác định primitive hay reference; với primitive, xét wrapper/unboxing và widening; với reference, xét `null` và quan hệ reference.
5. **Đang tra cứu overload?** Chỉ định đúng danh sách `Class<?>` theo chữ ký; `Method.invoke` không tự chọn overload thay bạn.
6. **Đang đọc kết quả hoặc field?** Nhớ rằng giao diện reflection trả về `Object` có thể boxing giá trị primitive; đừng kết luận ngược rằng kiểu khai báo là wrapper.

**Tự kiểm tra nhanh:** Nếu `Method m` biểu diễn `void f(long n)`, cả `m.getParameterTypes()[0] == long.class` và `long.class.isAssignableFrom(Integer.class) == false` đều đúng; song `m.invoke(instance, Integer.valueOf(3))` vẫn có thể gọi `f` thành công. Khả năng gọi đó đến từ *unboxing + widening primitive*, tuyệt đối không đến từ kế thừa.

## Ghi nhớ

- **Quan hệ kiểu:** `int` và `Integer` là hai kiểu khác nhau, không kế thừa lẫn nhau; `Integer` nằm trong cây lớp `Number → Object`.
- **Chuyển đổi giá trị:** boxing/unboxing và widening là conversion tại những ngữ cảnh được Java cho phép.
- **API Reflection:** `isAssignableFrom`/`isInstance` mô tả kiểu và đối tượng; `getMethod` yêu cầu chữ ký chính xác; `Method.invoke` và `Field.set` có quy tắc chuyển đổi đối số riêng.

Phân biệt ba tầng **type identity → method lookup → invocation conversion** sẽ giúp giải thích đúng mọi kết quả tưởng như «mâu thuẫn» giữa primitive và wrapper trong Java Reflection.
