# `instanceof` kiểm tra kiểu và kết quả khi đối tượng là `null` trong Java

> **Java core — language-basics / Mẫu kiểm tra kiểu**  
> **Môi trường:** Java 17+, không bật preview, chương trình một file và chỉ dùng JDK.  
> **Mục tiêu:** Hiểu `instanceof` kiểm tra kiểu đối tượng khi chạy, biết `null instanceof T` luôn là `false`, dùng pattern matching `instanceof` để xử lý an toàn, và tránh lỗi ép kiểu, phạm vi biến mẫu cùng hạn chế generic.

## 1. `instanceof` kiểm tra điều gì?

Toán tử `instanceof` trả về **`boolean`**, kiểm tra một tham chiếu có trỏ đến đối tượng thuộc kiểu tham chiếu cần kiểm tra hay không. Cú pháp cơ bản:

~~~java
Object value = "Java";

boolean isText = value instanceof String;       // true
boolean isSequence = value instanceof CharSequence; // true
boolean isNumber = value instanceof Number;    // false
~~~

`value` được khai báo kiểu `Object` nhưng đối tượng **thực tế lúc chạy** là `String`. Vì `String` triển khai `CharSequence`, cả hai phép kiểm tra đầu đều true.

`instanceof` không kiểm tra nội dung hoặc tính bằng nhau của hai đối tượng; đây là phép **kiểm tra quan hệ kiểu runtime**. Đừng nhầm nó với `==`, `equals()` hoặc `getClass() == SomeType.class`.

| Phép kiểm tra | Câu hỏi |
| --- | --- |
| `x instanceof T` | `x` khác null và đối tượng runtime tương thích với `T`? |
| `x == null` | Tham chiếu có đang null không? |
| `x.getClass() == T.class` | Lớp runtime có **chính xác** là `T`, không tính lớp con? |
| `x.equals(y)` | Hai đối tượng có bằng nhau theo ngữ nghĩa `equals` của lớp không? |

`getClass()` sẽ ném `NullPointerException` khi `x == null`; trái lại, `instanceof` **an toàn với null**.

## 2. `null instanceof T` luôn trả `false`

`null` nghĩa là **không có đối tượng nào**. Vì vậy tham chiếu null không phải là instance của bất kỳ kiểu lớp, interface hoặc kiểu mảng nào.

~~~java
Object value = null;

System.out.println(value instanceof Object); // false
System.out.println(value instanceof String); // false
System.out.println(value instanceof Runnable); // false
System.out.println(value instanceof int[]); // false
~~~

Kết quả này quan trọng ngay cả với `Object`: `null instanceof Object` cũng là false. Toán tử **không ném `NullPointerException`**, và phép kiểm tra trả true đồng thời xác nhận tham chiếu khác null.

Ví dụ:

~~~java
Object maybeText = null;

if (maybeText instanceof String) {
    System.out.println("String");
} else {
    System.out.println("Null or another type");
}
// In: Null or another type.
~~~

**Nhánh `else` không chứng minh đối tượng là null**: nó cũng nhận mọi đối tượng không phải `String`. Nếu cần phân biệt ba trạng thái, hãy kiểm tra null riêng:

~~~java
if (maybeText == null) {
    System.out.println("MISSING");
} else if (maybeText instanceof String) {
    System.out.println("TEXT");
} else {
    System.out.println("OTHER_TYPE");
}
~~~

## 3. Lớp con, interface và kiểu mảng

`instanceof` xem xét quan hệ kế thừa và triển khai interface, không chỉ lớp chính xác:

~~~java
class Animal {}
interface Named {}
class Dog extends Animal implements Named {}

Animal pet = new Dog();

boolean isAnimal = pet instanceof Animal; // true
boolean isDog = pet instanceof Dog;       // true
boolean isNamed = pet instanceof Named;   // true
~~~

Đối tượng runtime là `Dog` nên nó cũng là `Animal` và `Named`. Nếu tham chiếu `Animal` trỏ tới một `Cat` không triển khai `Named`, phép kiểm tra `Dog` hoặc `Named` sẽ false.

Mảng cũng là đối tượng:

~~~java
Object data = new int[] {1, 2};
boolean primitiveArray = data instanceof int[];   // true
boolean object = data instanceof Object;          // true
boolean referenceArray = data instanceof Object[]; // false
~~~

`int[]` không phải `Object[]`: mảng primitive chứa các giá trị `int`, không phải tham chiếu đối tượng. Với `String[]`, phép kiểm tra `instanceof Object[]` lại true vì các phần tử là tham chiếu.

## 4. Kiểm tra kiểu trước khi ép kiểu

Ép kiểu tham chiếu **không kiểm tra an toàn giúp bạn trước khi cast**; nếu đối tượng runtime không tương thích, Java ném `ClassCastException`:

~~~java
Object value = Integer.valueOf(7);

// String text = (String) value;
// Nếu chạy: ClassCastException.
~~~

Mẫu cũ thường viết:

~~~java
Object value = "Java";

if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length()); // 4
}
~~~

`instanceof String` là **điều kiện bảo vệ** trước phép cast. Nếu `value` null thì nhánh không chạy; nếu giá trị không phải String thì cũng không cast.

Một chi tiết dễ nhầm: **ép kiểu tham chiếu null có thể hợp lệ**:

~~~java
Object nothing = null;
String text = (String) nothing; // text vẫn null; cast không ném CCE.
// text.length(); // Nếu gọi: NullPointerException.
~~~

Nói cách khác, `instanceof` kiểm tra có đối tượng tương thích hay không; cast null không tạo ra đối tượng mới và không tự gọi phương thức.

## 5. Java 17: pattern matching với `instanceof`

Java 17 hỗ trợ cú pháp **type pattern** ngay trong phép kiểm tra:

~~~java
Object value = "hello";

if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // HELLO
}
~~~

Ở đây `text` là **biến mẫu** (*pattern variable*): khi kiểm tra true, Java tự thực hiện bước ràng buộc tham chiếu theo kiểu `String`. Nhờ đó không phải cast tường minh một lần nữa.

Biến mẫu chỉ được sử dụng nơi Java xác định rằng phép kiểm tra kiểu đã thành công (**flow scoping**):

~~~java
Object value = " Java ";

if (value instanceof String text && !text.isBlank()) {
    System.out.println(text.trim()); // Java
}
~~~

Với `&&`, vế phải chỉ được đánh giá khi kiểm tra kiểu true, nên `text` hợp lệ và không null ở vế phải. Trái lại:

~~~java
// KHÔNG BIÊN DỊCH: text không được đảm bảo đã có giá trị ở vế phải.
// if (value instanceof String text || text.isBlank()) { }
~~~

Trong `||`, vế phải chỉ chạy khi vế trái false, tức chưa thể gán biến mẫu `text`. Không dùng biến mẫu ngoài phạm vi mà trình biên dịch xác nhận.

## 6. Biến mẫu sau `return` và những giới hạn của kiểu

Một cách viết Java 17 rõ ràng là thoát sớm khi không khớp:

~~~java
static String uppercaseIfString(Object input) {
    if (!(input instanceof String text)) {
        return "NOT_TEXT";
    }
    return text.toUpperCase(); // text được xác định đã khớp.
}
~~~

Nếu điều kiện phủ định đúng, phương thức đã `return`. Khi luồng tới dòng cuối, Java biết `input instanceof String text` là true nên `text` có sẵn và khác null.

**Các giới hạn cần nhớ:**

- `instanceof` dùng cho **tham chiếu** ở Java 17; không thể viết `int x = 3; x instanceof Integer`. Muốn đưa số nguyên vào `Object`, autoboxing có thể tạo `Integer`.
- Kiểu bên phải phải phù hợp với ràng buộc kiểm tra runtime. Không thể thử trực tiếp `instanceof List<String>` vì thông tin tham số generic bị xóa (`type erasure`); có thể dùng `List<?>`.
- Với **type pattern**, Java 17 từ chối một số trường hợp mà kiểu tĩnh của biểu thức đã là subtype của kiểu mẫu (kiểm tra vô điều kiện). Ví dụ `String s = "a"; if (s instanceof String t)` là lỗi biên dịch; nếu đã biết kiểu `String`, không cần pattern như vậy.
- Pattern matching `instanceof` trong Java 17 chỉ giới thiệu type pattern; không phải cú pháp record pattern của các phiên bản Java mới.

Ví dụ với generic:

~~~java
Object value = java.util.List.of("A", "B");

if (value instanceof java.util.List<?> list) {
    System.out.println(list.size()); // 2
}

// KHÔNG BIÊN DỊCH: type argument String không kiểm tra được tại runtime.
// if (value instanceof java.util.List<String> list) { }
~~~

Kiểm tra `List<?>` không chứng minh các phần tử đều là String. Nếu nghiệp vụ cần kiểm tra loại phần tử, phải xem xét phần tử riêng, không dựa vào `instanceof List<String>`.

## 7. Chương trình Java 17+ chạy độc lập

Tạo file **InstanceofNullDemo.java**:

~~~java
import java.util.List;

public final class InstanceofNullDemo {
    interface Named {}

    static class Animal {}
    static final class Dog extends Animal implements Named {}
    static final class Cat extends Animal {}

    private static String describe(Object input) {
        if (input instanceof String text) {
            return "text:" + text.length();
        }
        if (input instanceof Dog dog) {
            return "dog:" + dog.getClass().getSimpleName();
        }
        return "other-or-null";
    }

    private static String safeUpper(Object input) {
        if (!(input instanceof String text)) {
            return "NOT_TEXT";
        }
        return text.toUpperCase();
    }

    public static void main(String[] args) {
        Object absent = null;
        System.out.println("nullObject=" + (absent instanceof Object));
        System.out.println("nullString=" + (absent instanceof String));
        System.out.println("nullNamed=" + (absent instanceof Named));
        System.out.println("nullArray=" + (absent instanceof int[]));

        Object word = "Java";
        System.out.println("wordString=" + (word instanceof String));
        System.out.println("wordCharSequence="
                + (word instanceof CharSequence));
        System.out.println("wordNumber=" + (word instanceof Number));

        Animal pet = new Dog();
        System.out.println("dogAnimal=" + (pet instanceof Animal));
        System.out.println("dogDog=" + (pet instanceof Dog));
        System.out.println("dogNamed=" + (pet instanceof Named));

        Animal cat = new Cat();
        System.out.println("catDog=" + (cat instanceof Dog));
        System.out.println("catNamed=" + (cat instanceof Named));

        Object primitiveArray = new int[] {1, 2};
        Object referenceArray = new String[] {"A", "B"};
        System.out.println("intArray=" + (primitiveArray instanceof int[]));
        System.out.println("intObjectArray="
                + (primitiveArray instanceof Object[]));
        System.out.println("strObjectArray="
                + (referenceArray instanceof Object[]));

        Object boxedNumber = Integer.valueOf(7);
        System.out.println("boxedInteger="
                + (boxedNumber instanceof Integer));

        Object list = List.of("A", "B");
        System.out.println("listWildcard=" + (list instanceof List<?>));

        System.out.println("describeNull=" + describe(null));
        System.out.println("describeText=" + describe("hello"));
        System.out.println("describeDog=" + describe(new Dog()));
        System.out.println("upperNull=" + safeUpper(null));
        System.out.println("upperText=" + safeUpper("java"));

        Object nothing = null;
        String castNull = (String) nothing;
        System.out.println("castNull=" + (castNull == null));

        try {
            String wrong = (String) boxedNumber;
            System.out.println("castValue=" + wrong);
        } catch (ClassCastException ex) {
            System.out.println("badCast=ClassCastException");
        }

        if (word instanceof String text && !text.isBlank()) {
            System.out.println("patternValue=" + text.toUpperCase());
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 InstanceofNullDemo.java
java InstanceofNullDemo
~~~

**Expected stdout chính xác:**

~~~text
nullObject=false
nullString=false
nullNamed=false
nullArray=false
wordString=true
wordCharSequence=true
wordNumber=false
dogAnimal=true
dogDog=true
dogNamed=true
catDog=false
catNamed=false
intArray=true
intObjectArray=false
strObjectArray=true
boxedInteger=true
listWildcard=true
describeNull=other-or-null
describeText=text:5
describeDog=dog:Dog
upperNull=NOT_TEXT
upperText=JAVA
castNull=true
badCast=ClassCastException
patternValue=JAVA
~~~

Đặc biệt, **bốn dòng `null...=false`** cho thấy `instanceof` không ném NPE khi tham chiếu là null. `intObjectArray=false` là do `int[]` không phải `Object[]`; `strObjectArray=true` do `String[]` là mảng tham chiếu. Biến mẫu `text` chỉ được sử dụng khi đã khớp kiểu.

## 8. Sai lầm phổ biến và bài tập

| Tình huống | Kết quả hoặc cách xử lý đúng |
| --- | --- |
| `null instanceof Object` | **false**, không ném `NullPointerException` |
| `x instanceof String` false | `x` có thể null **hoặc** thuộc kiểu khác |
| Cast đối tượng sai kiểu | Có thể ném `ClassCastException` |
| Cast `null` sang `String` | Hợp lệ, kết quả vẫn null |
| `x instanceof String s && !s.isBlank()` | Hợp lệ: `s` có mặt khi vế phải chạy |
| `x instanceof String s \|\| s.isBlank()` | Không hợp lệ về phạm vi biến mẫu |
| `x instanceof List<String>` | Không hợp lệ do type erasure; dùng `List<?>` khi cần kiểm tra raw shape |

**Bài 1.** Cho `Object x = null;`, dự đoán `x instanceof Object`, `x instanceof String` và `x instanceof Runnable`. Khi nào nên thêm `x == null`?

**Bài 2.** Cho `Object x = "Java";`, kiểm tra `String`, `CharSequence`, `Number`. Giải thích bằng quan hệ kiểu.

**Bài 3.** Viết `if (x instanceof String text)` để chỉ gọi `text.length()` khi an toàn. Thử truyền null và một `Integer`.

**Bài 4.** Giải thích vì sao `List<?>` dùng được trong `instanceof` nhưng `List<String>` không; điều kiện đó có chứng minh mọi phần tử là String không?

**Bài 5.** Viết phương thức nhận `Object` và trả một trong ba nhãn `"MISSING"`, `"TEXT"`, `"OTHER"` mà không cast sai kiểu và không làm mất sự phân biệt null.

### Ghi nhớ

**`instanceof` trả true chỉ khi tham chiếu khác null và đối tượng runtime tương thích với kiểu đích.** Vì vậy `null instanceof T` luôn false. Với Java 17, dùng `instanceof T name` để kiểm tra kiểu và lấy biến mẫu an toàn; chú ý phạm vi biến theo luồng, giới hạn generic, và đừng nhầm `instanceof` với ép kiểu hoặc kiểm tra null riêng.
