# Enum có thân riêng trên hằng: getClass và getDeclaringClass

## 1. Một kiểu enum có thể có nhiều lớp thực tế

Một enum có thể khai báo hành vi chung và cho một số hằng ghi đè hành vi bằng **thân lớp riêng của hằng (constant-specific class body)**. Ví dụ một phép biến đổi mặc định giữ nguyên số, còn các hằng khác nhân đôi hoặc nhân ba.

Các hằng ấy vẫn thuộc cùng một kiểu enum. Tuy nhiên, một hằng có thân lớp riêng được thực hiện bằng một lớp con ẩn danh của enum. Vì thế, **lớp thực tế của đối tượng** và **lớp enum khai báo hằng** có thể khác nhau.

Java cung cấp hai API trả lời hai câu hỏi đó:

| Lời gọi trên một hằng enum | Câu hỏi được trả lời |
| --- | --- |
| `constant.getClass()` | Đối tượng hằng này có lớp thực tế nào lúc chạy? |
| `constant.getDeclaringClass()` | Hằng này thuộc enum được khai báo nào? |

`getClass()` được kế thừa từ `Object`. `getDeclaringClass()` trong bảng là phương thức của `Enum`. Cả hai đều là phương thức `final`; người viết enum không ghi đè chúng để thay đổi kết quả.

Sự phân biệt này có giá trị khi một bộ chuyển đổi, bộ kiểm tra dữ liệu hoặc nơi lưu cấu hình dùng `Class` làm khóa. Nếu các quy tắc được đăng ký cho kiểu enum chung, dùng lớp riêng của từng hằng để tra cứu có thể làm mất cấu hình.

## 2. Thân riêng tạo lớp con, còn hằng vẫn thuộc enum ban đầu

Xét cấu trúc:

~~~java
enum Transform {
    IDENTITY,
    DOUBLE {
        @Override
        public int apply(int value) {
            return value * 2;
        }
    };

    public int apply(int value) {
        return value;
    }
}
~~~

Đây là một khai báo enum hoàn chỉnh, có thể đặt trong một lớp hoặc trong tệp nguồn phù hợp; chưa phải chương trình có `main`.

- `IDENTITY` không có thân riêng, nên dùng phần thực hiện `apply` trong `Transform`.
- `DOUBLE` có thân riêng và ghi đè `apply`.
- Lớp thực tế của `IDENTITY` là `Transform`.
- Lớp thực tế của `DOUBLE` là lớp con ẩn danh của `Transform`.
- Cả hai đều có `getDeclaringClass() == Transform.class`.

Không cần có phương thức ghi đè thì thân riêng mới tạo lớp con: ngay cả một thân `{}` rỗng trên hằng cũng có ý nghĩa về lớp như vậy.

Đây là cơ chế Java dành riêng cho khai báo hằng enum. Nó không cho phép mã ứng dụng tùy ý viết một lớp khác `extends Transform` để bổ sung hằng. Các hằng vẫn là tập giá trị được khai báo của enum.

Trên Java 17, enum không có thân riêng trên hằng là `final` ngầm định; enum có ít nhất một thân như vậy là `sealed` ngầm định. Vì vậy, một công cụ Reflection không nên dựa vào giả định “mọi lớp enum đều có modifier final” để nhận diện enum; hãy dùng API đúng mục đích như `Class.isEnum()`.

## 3. Ví dụ chạy được: cùng kiểu enum, khác lớp thực tế

Lưu thành `EnumBodyIdentityDemo.java`:

~~~java
public class EnumBodyIdentityDemo {
    enum Transform {
        IDENTITY,
        DOUBLE {
            @Override
            public int apply(int value) {
                return value * 2;
            }
        },
        TRIPLE {
            @Override
            public int apply(int value) {
                return value * 3;
            }
        };

        public int apply(int value) {
            return value;
        }
    }

    private static void inspect(Transform transform) {
        System.out.println(
                transform.name()
                + " value=" + transform.apply(4)
                + " exact=" + (transform.getClass() == Transform.class)
                + " enumClass=" + transform.getClass().isEnum());
    }

    public static void main(String[] args) {
        for (Transform transform : Transform.values()) {
            inspect(transform);
        }

        System.out.println("DOUBLE.superIsTransform="
                + (Transform.DOUBLE.getClass().getSuperclass()
                   == Transform.class));
        System.out.println("IDENTITY.superIsEnum="
                + (Transform.IDENTITY.getClass().getSuperclass()
                   == Enum.class));
        System.out.println("DOUBLE.anonymous="
                + Transform.DOUBLE.getClass().isAnonymousClass());
        System.out.println("sameRuntime="
                + (Transform.DOUBLE.getClass()
                   == Transform.TRIPLE.getClass()));
        System.out.println("sameDeclaring="
                + (Transform.DOUBLE.getDeclaringClass()
                   == Transform.TRIPLE.getDeclaringClass()));
        System.out.println("sameConstant="
                + (Transform.DOUBLE == Transform.TRIPLE));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 EnumBodyIdentityDemo.java
java EnumBodyIdentityDemo
~~~

Kết quả:

~~~text
IDENTITY value=4 exact=true enumClass=true
DOUBLE value=8 exact=false enumClass=false
TRIPLE value=12 exact=false enumClass=false
DOUBLE.superIsTransform=true
IDENTITY.superIsEnum=true
DOUBLE.anonymous=true
sameRuntime=false
sameDeclaring=true
sameConstant=false
~~~

Hãy đọc kết quả thành ba lớp thông tin:

1. **Hành vi:** cùng một lời gọi `apply(4)` chọn phần thực hiện tương ứng với hằng. Đó là đa hình thông thường.
2. **Lớp thực tế:** `DOUBLE` và `TRIPLE` có hai lớp riêng khác nhau; `IDENTITY` dùng trực tiếp lớp `Transform`.
3. **Kiểu enum:** cả ba đều là hằng của `Transform`. Có cùng lớp khai báo enum không có nghĩa là hai hằng bằng nhau.

Chương trình không in tên nhị phân của các lớp ẩn danh. Tên do trình biên dịch tạo ra thường chứa `$` và số, nhưng không phải dữ liệu nghiệp vụ ổn định. So sánh đối tượng `Class` và hỏi đúng API giúp ví dụ không phụ thuộc các tên ấy.

## 4. Vì sao getClass().isEnum() có thể trả false?

`Class.isEnum()` nhận diện lớp được khai báo là enum. Lớp riêng của một hằng là lớp con ẩn danh; nó không phải chính khai báo enum ban đầu.

Do đó, với ví dụ vừa chạy:

~~~java
Transform.DOUBLE.getClass().isEnum()          // false
Transform.DOUBLE.getDeclaringClass().isEnum() // true
~~~

Hai biểu thức trên là các dòng minh họa trong phạm vi lớp `EnumBodyIdentityDemo`.

Kết quả `false` ở dòng đầu không làm `DOUBLE` mất tư cách hằng enum. Nó chỉ mô tả đúng lớp đang được hỏi.

Khi nhận một đối tượng bất kỳ, có thể kiểm tra:

~~~java
if (value instanceof Enum<?> constant) {
    Class<?> enumType = constant.getDeclaringClass();
    System.out.println(enumType.isEnum());
}
~~~

Đây là đoạn bên trong một phương thức có tham số `Object value`. `instanceof` kiểm tra đối tượng có thuộc hệ kiểu `Enum` hay không, nên bao gồm cả hằng có lớp riêng. Với `null`, điều kiện là `false`.

Không dùng `value.getClass().isEnum()` thay thế điều kiện trên nếu mục tiêu là nhận diện mọi đối tượng hằng enum. Cũng không dùng riêng `Enum.class.isAssignableFrom(type)` để khẳng định `type` là một khai báo enum: quan hệ kế thừa rộng hơn điều kiện `isEnum()`, và bản thân `Enum.class` cũng thỏa kiểm tra quan hệ với chính nó.

## 5. Áp dụng: chuẩn hóa khóa cấu hình theo kiểu enum

Giả sử cấu hình được đăng ký một lần cho enum `Shipping`. Mỗi hằng, kể cả hằng có thân riêng, đều phải tìm được cùng cấu hình ấy.

Lưu thành `EnumTypeRegistryDemo.java`:

~~~java
import java.util.Map;
import java.util.Objects;

public class EnumTypeRegistryDemo {
    enum Shipping {
        BASIC,
        PRIORITY {
            @Override
            public String label() {
                return "Priority delivery";
            }
        };

        public String label() {
            return "Basic delivery";
        }
    }

    static Class<?> enumTypeOf(Object value) {
        Objects.requireNonNull(value, "value");
        if (value instanceof Enum<?> constant) {
            return constant.getDeclaringClass();
        }
        throw new IllegalArgumentException("Expected an enum constant");
    }

    public static void main(String[] args) {
        Map<Class<?>, String> configuration =
                Map.of(Shipping.class, "shipping-config");

        Enum<?> value = Shipping.PRIORITY;

        System.out.println("wrong="
                + configuration.get(value.getClass()));
        System.out.println("right="
                + configuration.get(value.getDeclaringClass()));
        System.out.println("sameLogicalType="
                + (enumTypeOf(Shipping.BASIC)
                   == enumTypeOf(Shipping.PRIORITY)));
        System.out.println("expectedExactClass="
                + (value.getClass() == Shipping.class));
        System.out.println("expectedIsInstance="
                + Shipping.class.isInstance(value));
        System.out.println("enumAccessor="
                + (value.getDeclaringClass() == Shipping.class));
        System.out.println("classAccessor.owner="
                + (Shipping.class.getDeclaringClass()
                   == EnumTypeRegistryDemo.class));
        System.out.println("anonymousClassAccessor="
                + value.getClass().getDeclaringClass());
        System.out.println("knownName=" + value.name());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 EnumTypeRegistryDemo.java
java EnumTypeRegistryDemo
~~~

Kết quả:

~~~text
wrong=null
right=shipping-config
sameLogicalType=true
expectedExactClass=false
expectedIsInstance=true
enumAccessor=true
classAccessor.owner=true
anonymousClassAccessor=null
knownName=PRIORITY
~~~

Khóa `Shipping.class` và lớp riêng của `PRIORITY` là hai đối tượng `Class` khác nhau. Vì vậy, phép tra cứu đầu trả `null`. Lấy `getDeclaringClass()` cho đúng khóa enum đã được đăng ký.

Một lỗi như vậy có thể khó phát hiện khi chỉ thử hằng không có thân riêng: với `BASIC`, `getClass()` tình cờ trả chính `Shipping.class`, nên phép tra cứu có vẻ hoạt động.

Hàm `enumTypeOf` xác định hợp đồng rõ ràng: chỉ nhận một đối tượng hằng enum, từ chối `null` và các đối tượng khác. Không nên âm thầm lấy một lớp cha bất kỳ cho đầu vào không phải enum.

Nếu mục tiêu là kiểm tra một đối tượng có gán được cho kiểu đích hay không, `Shipping.class.isInstance(value)` phản ánh quan hệ kiểu phù hợp, bao gồm lớp con của hằng. Kiểm tra `value.getClass() == Shipping.class` đòi hỏi lớp thực tế phải trùng tuyệt đối và sẽ từ chối hằng có thân riêng.

## 6. Hai phương thức cùng tên getDeclaringClass không có cùng ngữ nghĩa

Đây là điểm dễ đọc nhầm khi viết chuỗi lời gọi Reflection:

| Biểu thức trong ví dụ Shipping | Đối tượng nhận lời gọi | Ý nghĩa |
| --- | --- | --- |
| `value.getDeclaringClass()` | Một hằng kiểu `Enum<?>` | Lấy lớp enum `Shipping` |
| `Shipping.class.getDeclaringClass()` | Một đối tượng `Class` | Lấy lớp chứa khai báo lớp thành viên `Shipping` |
| `value.getClass().getDeclaringClass()` | Một đối tượng `Class` của lớp thực tế | Hỏi lớp khai báo của lớp thực tế ấy |

Trong chương trình, `Shipping` là enum thành viên của `EnumTypeRegistryDemo`, nên `Shipping.class.getDeclaringClass()` trả lớp ngoài `EnumTypeRegistryDemo`.

Ngược lại, lớp ẩn danh của `PRIORITY` không phải một lớp thành viên có tên; `Class.getDeclaringClass()` trả `null` cho lớp ẩn danh. Vì vậy, thêm `getClass()` trước lời gọi đã làm đổi API và đổi câu hỏi.

Khi đọc mã, hãy nhìn kiểu của đối tượng đứng trước dấu chấm:

- `Enum.getDeclaringClass()` xác định **kiểu enum của hằng**.
- `Class.getDeclaringClass()` xác định **lớp khai báo một lớp thành viên**.

Không thay thế hai API này cho nhau dù tên phương thức giống nhau. Với một enum ở mức cao nhất của tệp, `Class.getDeclaringClass()` cũng không phải cách tìm lại enum ấy; nó trả `null` vì không có lớp chứa khai báo thành viên.

## 7. Chọn lớp nào khi đọc metadata?

Chọn `Class` theo thông tin thực sự cần:

**Muốn xử lý kiểu enum chung:** lấy `constant.getDeclaringClass()`. Đây là điểm bắt đầu phù hợp để lấy danh sách hằng bằng `getEnumConstants()`, tra cấu hình theo kiểu, hoặc tìm các khai báo chung của enum.

**Muốn điều tra phần thực hiện riêng của một hằng:** dùng `constant.getClass()`. Khi đó, việc thấy một lớp ẩn danh và các phương thức ghi đè là dữ liệu mong muốn.

Hai hướng không thể tùy ý tráo đổi. Chẳng hạn, `getDeclaredMethods()` hỏi các phương thức được khai báo trực tiếp trong lớp đang xét. Hỏi lớp riêng của `DOUBLE` sẽ nhìn vào phần khai báo riêng của hằng; hỏi `Transform.class` sẽ nhìn vào khai báo enum chung.

Một phương thức chỉ được thêm trong thân riêng của hằng không tự trở thành phương thức chung có thể gọi qua mọi biến kiểu enum. Khi thiết kế hành vi đa hình, nên khai báo phương thức trong enum rồi ghi đè ở hằng cần thay đổi, như `apply` trong ví dụ.

Nếu enum khai báo một phương thức `abstract`, mỗi hằng phải cung cấp phần thực hiện theo quy tắc của enum. Khi tất cả hằng có thân riêng, có thể không có hằng nào mang trực tiếp lớp thực tế của enum. Vì vậy, chọn một hằng bất kỳ làm “mẫu” rồi lấy `getClass()` vẫn không xác định đúng kiểu enum chung.

Không cần `setAccessible(true)`, sửa field nội bộ hoặc tìm constructor để phân biệt hai loại lớp này. Các API công khai đã cung cấp quan hệ cần thiết.

## 8. Những cách suy đoán dễ sai

| Cách làm | Vì sao dễ sai | Cách phù hợp |
| --- | --- | --- |
| `constant.getClass() == ExpectedEnum.class` để nhận mọi hằng của enum | Không nhận lớp riêng của hằng | So sánh `getDeclaringClass()` hoặc dùng `ExpectedEnum.class.isInstance` theo mục đích |
| Lấy `getSuperclass()` đúng một lần cho mọi hằng | Hằng thường có lớp cha là `Enum`; hằng có thân riêng có lớp cha là enum cụ thể | Dùng `Enum.getDeclaringClass()` |
| Cắt tên lớp tại dấu `$` | Dấu này còn xuất hiện trong tên lớp lồng; tên lớp ẩn danh không phải khóa nghiệp vụ | Giữ đối tượng `Class` trả từ API |
| Dựa vào một hằng để đoán lớp của mọi hằng | Enum có thể trộn hằng có và không có thân riêng | Chuẩn hóa từng hằng về lớp enum khi cần |
| Nghĩ hai hằng khác lớp thực tế là khác kiểu enum | Lẫn lớp triển khai với kiểu enum khai báo | Kiểm tra `getDeclaringClass()` |
| Nghĩ cùng lớp enum nghĩa là cùng hằng | Các hằng khác nhau cùng thuộc một enum | So sánh hằng hoặc dùng `name()` theo hợp đồng |
| Gọi `getClass().getDeclaringClass()` thay cho `getDeclaringClass()` | Đã chuyển sang API trên `Class` | Gọi trực tiếp phương thức của `Enum` |

Ngoài ra, tên lớp giống nhau không bảo đảm đó là cùng kiểu nếu chúng được nạp bởi các bộ nạp lớp khác nhau. Khi lưu metadata trong phạm vi JVM, dùng đối tượng `Class` làm khóa giúp giữ đúng danh tính kiểu mà các API trả về; không tự rút gọn thành tên đơn giản rồi giả định mọi tên trùng nhau là cùng kiểu.

## 9. Tự kiểm tra

1. Nếu `RED` và `BLUE` cùng có thân riêng trong enum `Color`, `RED.getClass() == BLUE.getClass()` có đúng không?
2. Hai hằng ấy có cùng `getDeclaringClass()` không?
3. Nếu một hằng không có thân riêng, vì sao lấy một lần `getSuperclass()` không phải cách chuẩn hóa tổng quát?
4. `value.getClass().getDeclaringClass()` có tương đương `value.getDeclaringClass()` không?
5. Một nơi lưu cấu hình đăng ký theo `Color.class` nên dùng API nào để lấy khóa từ một hằng?
6. Có cần in hoặc phân tích các tên lớp dạng có dấu `$` để trả lời các câu hỏi trên không?

Đáp án:

1. Không. Mỗi thân riêng tương ứng với một lớp con ẩn danh riêng.
2. Có; cả hai đều trả `Color.class`.
3. Lớp thực tế của hằng thường chính là enum, nên lớp cha của nó là `Enum`, không phải enum cần tìm.
4. Không. Một lời gọi hỏi quan hệ khai báo của `Class`; lời gọi còn lại hỏi kiểu enum của hằng.
5. `constant.getDeclaringClass()`.
6. Không. Các đối tượng `Class` và API quan hệ kiểu đã trả lời trực tiếp.

Khi viết mã Reflection xử lý enum, hãy quyết định rõ đang cần lớp thực hiện hành vi của một hằng hay cần kiểu enum chung. Quyết định đó xác định lựa chọn giữa `getClass()` và `Enum.getDeclaringClass()`.

## Tài liệu đối chiếu

- [Java 17 — Object.getClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#getClass()).
- [Java 17 — Enum.getDeclaringClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html#getDeclaringClass()).
- [Java 17 — Class.getDeclaringClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getDeclaringClass()).
- [JLS 17 — Khai báo enum và thân riêng trên hằng](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9).
