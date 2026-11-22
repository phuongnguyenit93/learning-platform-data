# Quan hệ với `java.lang.Record` và tính `final` của lớp

> **Phạm vi học tập:** Bài thuộc chủ đề **Java 14 → Nền tảng record**, nhưng chỉ trình bày cú pháp và hợp đồng **record class đã ổn định trong Java hiện hành**. `record` từng xuất hiện dưới dạng preview ở Java 14 và trở thành tính năng chính thức từ **Java 16** (JEP 395). Với chương trình mới, dùng một JDK được nhà cung cấp tiếp tục bảo trì; các ví dụ chạy với **Java 17+** và không dùng `--enable-preview`. Điểm trọng tâm của bài là **quan hệ kế thừa `Object → Record → record class`** và **lý do record luôn là lớp `final`**.

## 1. Mục tiêu

Sau bài này, bạn cần giải thích và vận dụng được:

1. `java.lang.Record` là **lớp cơ sở trừu tượng (abstract class)** của các record Java; nó **không phải** từ khóa `record` và **không phải** interface.
2. Mỗi record class có **lớp cha trực tiếp** là `java.lang.Record`, dù trong khai báo không viết `extends`; `Record` lại kế thừa `Object`.
3. Record class **ngầm định là `final`**: có thể tạo đối tượng nhưng không thể tạo subclass; không được khai báo `abstract`, `sealed`, `non-sealed` cho chính record.
4. Record **không được `extends` bất cứ lớp nào**, kể cả viết tường minh `extends java.lang.Record`; tuy nhiên **được `implements` interface**, kể cả sealed interface được cho phép.
5. `final` trên record class **không đồng nghĩa** tất cả dữ liệu mà record tham chiếu đều bất biến sâu.
6. Dùng `Class.isRecord()`, `getSuperclass()`, `getRecordComponents()` và `Modifier.isFinal()` để kiểm tra bằng reflection.

## 2. Hệ phân cấp lớp: `Object → Record → MyRecord`

Khai báo record đơn giản:

```java
record Point(int x, int y) {}
```

Hệ phân cấp thực tế của nó là:

```text
java.lang.Object
        |
        v
java.lang.Record  (abstract)
        |
        v
Point             (final, record class)
```

**Giải thích từng mức:**

- `java.lang.Object` là lớp gốc của hệ phân cấp lớp Java.
- `java.lang.Record` thuộc module `java.base`, package `java.lang`. Nó khai báo dạng `public abstract class Record extends Object`; đây là **lớp cha chung của mọi record class do ngôn ngữ Java khai báo**.
- `Point` là một lớp Java thật, có kiểu `Point`, constructor, methods và thông tin phản chiếu; compiler đặt `Record` làm **direct superclass** theo JLS `8.10`. `Point` đồng thời là subtype của `Record` và `Object`.
- `Point` ngầm định là `final` nên **không tồn tại lớp `ColoredPoint extends Point`**.

Cách viết `record Point(int x, int y) {}` không phải cú pháp viết ngắn của `class Point extends Object`. Nó là một **record declaration** với quy tắc riêng về superclass, component, constructor và các phương thức của lớp.

**Hai loại quan hệ cần phân biệt:**

- **Kế thừa lớp:** `Point → Record → Object`, tối đa một lớp cha trực tiếp.
- **Thực thi interface:** `Point implements Named` là một quan hệ loại khác; record vẫn có thể tham gia đa hình qua interface.

### 2.1. `java.lang.Record` cung cấp điều gì?

Javadoc hiện hành định nghĩa `Record` là lớp `abstract` có constructor `protected Record()` và ba phương thức trừu tượng:

| Thành viên của `Record` | Vai trò |
| --- | --- |
| `public abstract boolean equals(Object other)` | Hợp đồng so sánh bằng nhau của record. |
| `public abstract int hashCode()` | Hợp đồng mã băm nhất quán với `equals`. |
| `public abstract String toString()` | Biểu diễn dạng văn bản của đối tượng record. |
| `protected Record()` | Constructor dùng trong quá trình tạo các lớp record; không phải API để ứng dụng trực tiếp khởi tạo `Record`. |

Mỗi record class phải có các implementation của ba phương thức. Nếu bạn không tự khai báo, compiler sẽ sinh implementation dựa trên các **record components**. Những component như `x`, `y` trong `Point(int x, int y)` được biểu diễn bằng **field `private final` ở chính `Point`**, cùng accessor `x()`, `y()` và canonical constructor. Chúng **không phải** field khai báo trong `java.lang.Record`.

`Record` vẫn thừa hưởng các thành viên thích hợp từ `Object`, chẳng hạn `getClass()`. Vì vậy đối tượng `Point` dùng được những thao tác thông thường của một đối tượng Java; chúng không biến `Record` thành một kiểu dữ liệu thông thường mà ta có thể tự tạo bằng `new Record()`.

**Không gọi `new Record()`:** `Record` là abstract nên không có instance trực tiếp. **Không tự viết class thường `extends Record`:** JLS `8.1.4` giới hạn `Record` chỉ được kế thừa bởi **record class**. Bạn phải dùng cú pháp `record` để khai báo loại này.

### 2.2. `java.lang.Record` và từ khóa `record` không phải một thứ

| Viết trong mã | Ý nghĩa |
| --- | --- |
| `record Point(int x, int y) {}` | Tạo một **record class** tên `Point` theo cú pháp ngôn ngữ. |
| `java.lang.Record` | Kiểu **abstract superclass** mà record class kế thừa ngầm. |
| `Record value = new Point(2, 3);` | Biến kiểu `Record` giữ tham chiếu đến một đối tượng record cụ thể. |
| `Point.class.isRecord()` | Trả về `true` vì `Point` được khai báo bằng `record`. |
| `Record.class.isRecord()` | Trả về `false`: `Record` là **base class**, bản thân nó không được khai báo bằng cú pháp `record`. |

Phép `Record.class.isAssignableFrom(Point.class)` trả `true` vì quan hệ subtype. Ngược lại, việc một lớp thường có tên giống `Record` hoặc có các phương thức `equals`/`hashCode`/`toString` không khiến lớp đó thành record class.

## 3. Vì sao record class luôn là `final`?

Theo JLS `8.10`: **mọi record class đều ngầm định `final`**. Có thể viết từ khóa `final` tường minh nhưng chỉ là lặp lại điều compiler đã biết.

```java
record Point(int x, int y) {}

// Hợp lệ, nhưng từ khóa final là dư:
final record Size(int width, int height) {}
```

Điều này có hai hệ quả:

**Hệ quả thứ nhất — Không được mở rộng một record class:**

```java
record Point(int x, int y) {}

// CỐ Ý SAI, KHÔNG BIÊN DỊCH:
class ColoredPoint extends Point {
    // ...
}
```

Compiler từ chối vì `Point` là final. Không có ngoại lệ cho một record khác, nested class hay package cùng tên: record đã đóng việc kế thừa lớp ở cấp khai báo.

**Hệ quả thứ hai — Không được khai báo record là abstract hoặc sealed:**

```java
// Các khai báo dưới đây đều KHÔNG HỢP LỆ:
abstract record A(int x) {}
sealed record B(int x) permits C {}
non-sealed record D(int x) {}
```

Theo JLS hiện hành, record class không thể có các modifier `abstract`, `sealed` hoặc `non-sealed`. Một record luôn là kiểu cụ thể với đầy đủ các component; modifier `final` được phép nhưng không cần thiết.

### 3.1. Có thể viết `extends Record` cho «rõ ràng» không?

**Không.** Cú pháp record declaration **không có `extends` clause**:

```java
// CỐ Ý SAI:
record Point(int x, int y) extends Record {}
```

Lỗi không phải vì thiếu import: ngay cả `extends java.lang.Record` cũng không được phép. Lớp cha `Record` được ngôn ngữ ấn định tự động; việc khai báo tường minh không hợp lệ. Tương tự, `record Point(...) extends MyBase` không tồn tại cú pháp hợp lệ.

Với nhu cầu **kế thừa một lớp cơ sở có trạng thái hoặc hành vi**, hãy cân nhắc lớp thường (nếu đúng mô hình miền nghiệp vụ). Nếu chỉ cần chia sẻ **hợp đồng hành vi**, hãy dùng interface cho các record. Không cố ép một cây kế thừa class vào cấu trúc record.

### 3.2. Final của lớp khác final của field

Cần tách ba ý:

- **`final` của class:** không cho subclass, như mọi record class.
- **`final` của component field:** sau khi tạo record, tham chiếu hoặc giá trị field tương ứng không được gán lại trực tiếp.
- **Bất biến sâu (deep immutability):** đối tượng được tham chiếu bởi field cũng không thể thay đổi — điều này **không tự đến từ `record`**.

Ví dụ `record Box(int[] values) {}` có component field `values` là final nhưng các phần tử của array do `values` trỏ tới **vẫn có thể đổi**. Phần cuối bài trình bày cách xử lý khi dùng dữ liệu mutable.

## 4. Record vẫn được `implements` interface

Không thể có `extends MyBase`, nhưng record **được thực thi một hoặc nhiều interface**. Đây là cách tự nhiên để chia sẻ hợp đồng sử dụng và hỗ trợ đa hình.

```java
interface Named {
    String name();
}

record User(String name, int age) implements Named {}
```

Record component `name` tạo accessor công khai `name()` có cùng chữ ký với phương thức ở `Named`. Vì thế compiler cho phép `User` thỏa interface mà không cần viết lại method.

```java
Named value = new User("An", 22);
System.out.println(value.name());  // An
```

Biến `value` có kiểu compile-time là `Named`; API mà code có thể gọi là những gì `Named` công bố. Đó là **đa hình qua interface**. `User` vẫn là một lớp `final`.

Record cũng có thể khai báo instance methods thường, static methods, static fields và constructors hợp lệ. Việc lớp là `final` không cấm thêm hành vi; chỉ cấm tạo subclass. Ví dụ:

```java
record Distance(int meters) {
    public Distance {
        if (meters < 0) {
            throw new IllegalArgumentException("meters must be >= 0");
        }
    }

    double kilometers() {
        return meters / 1000.0;
    }
}
```

`Distance` vẫn có canonical constructor, accessor `meters()`, cùng các phương thức `equals/hashCode/toString`. Method `kilometers()` là hành vi bổ sung, **không phải** record component mới. Compiler không cho khai báo thêm **instance field** bên ngoài các field tương ứng với component; muốn thêm một giá trị là phần trạng thái của record, hãy biểu diễn nó trong header, nếu phù hợp với mô hình.

## 5. Chương trình Java hoàn chỉnh: kiểm tra superclass, `final` và reflection

Lưu file **`RecordHierarchyDemo.java`**. Chương trình dùng record, interface và các API reflection chính thức:

```java
import java.lang.reflect.Modifier;
import java.lang.reflect.RecordComponent;

public class RecordHierarchyDemo {
    interface Named {
        String name();
    }

    record User(String name, int age) implements Named {
        User {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name is blank");
            }
            if (age < 0) {
                throw new IllegalArgumentException("negative age");
            }
        }

        String description() {
            return name + ":" + age;
        }
    }

    static void acceptRecord(Record value) {
        System.out.println("record-ref=" + value.getClass().getSimpleName());
    }

    public static void main(String[] args) {
        User user = new User("An", 22);
        Named asNamed = user;
        Record asRecord = user;
        Object asObject = user;

        System.out.println("parent=" + User.class.getSuperclass().getName());
        System.out.println("final=" + Modifier.isFinal(User.class.getModifiers()));
        System.out.println("isRecord=" + User.class.isRecord());
        System.out.println("Record-isRecord=" + Record.class.isRecord());
        System.out.println(
            "Record-assignable=" + Record.class.isAssignableFrom(User.class)
        );

        System.out.println("name=" + asNamed.name());
        System.out.println("description=" + user.description());
        System.out.println("equals=" + user.equals(new User("An", 22)));
        System.out.println("object-type=" + asObject.getClass().getSimpleName());

        for (RecordComponent component : User.class.getRecordComponents()) {
            System.out.println(
                "component=" + component.getName()
                + ":" + component.getType().getSimpleName()
            );
        }

        acceptRecord(asRecord);
    }
}
```

Biên dịch bằng một JDK **17 trở lên** có hỗ trợ target 17:

```bash
javac --release 17 RecordHierarchyDemo.java
java RecordHierarchyDemo
```

**Stdout dự kiến chính xác:**

```text
parent=java.lang.Record
final=true
isRecord=true
Record-isRecord=false
Record-assignable=true
name=An
description=An:22
equals=true
object-type=User
component=name:String
component=age:int
record-ref=User
```

**Giải thích các dòng quan trọng:**

1. `getSuperclass()` trả **`java.lang.Record`** chứ không phải `java.lang.Object`; `Object` là superclass gián tiếp.
2. `Modifier.isFinal(...)` trả `true` dù trong source chỉ viết `record User(...)`.
3. `User.class.isRecord()` trả `true`; `Record.class.isRecord()` trả `false`. Reflection phân biệt rõ **record class** và **class gốc tên Record**.
4. `isAssignableFrom` xác nhận `User` là subtype của `Record`.
5. `Named` thể hiện đa hình qua interface; `Record` thể hiện đa hình qua superclass. Cả hai tham chiếu đều trỏ tới **chính đối tượng `User`**.
6. `getRecordComponents()` trả về metadata của hai component theo thứ tự khai báo: `name` kiểu `String` và `age` kiểu `int`. Các component không trở thành các field công khai của `Record`.
7. Hai instance `User("An", 22)` được so sánh bằng nhau nhờ implementation `equals` theo component mà compiler sinh.

**Chú ý:** Khi một biến có kiểu `Record`, Java không tự cho gọi `asRecord.name()` hoặc `asRecord.age()`, vì những accessor ấy **không nằm trong API của `java.lang.Record`**. Dùng kiểu `User` hoặc một interface có khai báo hành vi phù hợp. Reflection hữu ích khi cần xử lý metadata động nhưng không nên thay cho một API typed rõ ràng ở logic nghiệp vụ.

## 6. Record `final` vẫn kết hợp được với `sealed interface`

Một `sealed interface` giới hạn tập kiểu được phép thực thi. Record là `final` sẵn, nên thích hợp làm **nhánh cuối** (leaf type) trong mô hình miền đóng. Đây là khả năng Java đã ổn định từ **Java 17**, không cần `sealed record`.

Lưu thành **`SealedRecordDemo.java`**:

```java
public class SealedRecordDemo {
    sealed interface Result permits Success, Failure {}

    record Success(int value) implements Result {}
    record Failure(String reason) implements Result {}

    static String describe(Result result) {
        if (result instanceof Success success) {
            return "ok=" + success.value();
        }
        if (result instanceof Failure failure) {
            return "error=" + failure.reason();
        }
        throw new IllegalStateException("Unexpected Result");
    }

    public static void main(String[] args) {
        Result one = new Success(42);
        Result two = new Failure("denied");

        System.out.println(describe(one));
        System.out.println(describe(two));
        System.out.println(Success.class.isRecord());
    }
}
```

```bash
javac --release 17 SealedRecordDemo.java
java SealedRecordDemo
```

**Stdout:**

```text
ok=42
error=denied
true
```

Ở đây `Result` là **sealed interface**; `Success` và `Failure` là **final record classes** được phép implements nó. `Success` không thể extends `Failure` hay ngược lại. `instanceof` với type pattern là tính năng ổn định từ Java 16, dùng được trong mục tiêu 17 của ví dụ.

Trường hợp muốn thêm loại kết quả mới cần thay đổi hợp đồng `Result` và khai báo danh sách subtype được cho phép. Đây là kiểm soát mô hình kiểu bằng **interface**, không phải kế thừa record.

## 7. `final` không bảo đảm bất biến sâu: bẫy array và collection

Một record thường được dùng như kiểu dữ liệu mang giá trị bất biến, nhưng **final chỉ giữ cố định các component field**, không khóa toàn bộ object graph.

### 7.1. Array vẫn có thể thay đổi

```java
record Numbers(int[] items) {}

int[] source = {1, 2};
Numbers numbers = new Numbers(source);

source[0] = 99;
System.out.println(numbers.items()[0]); // 99
```

Đây là đoạn minh họa **nằm trong phương thức** (không phải toàn bộ chương trình độc lập). Mặc dù `Numbers` final và field `items` final, array vẫn bị sửa thông qua một tham chiếu có sẵn. Accessor `items()` cũng trả về tham chiếu array ấy.

Ngoài ra, mặc định `equals` của record so sánh component tham chiếu dựa trên `equals` của kiểu đó. Với array, `equals` mặc định là **so sánh danh tính tham chiếu**, không so nội dung:

```java
Numbers first = new Numbers(new int[]{1});
Numbers second = new Numbers(new int[]{1});
System.out.println(first.equals(second)); // false
```

Không đánh đồng «record là value carrier» với «mọi loại component đều có deep equality». Với dữ liệu array/collection, xác định rõ ngữ nghĩa bình đẳng và khả năng sửa đổi trước khi chọn component type.

### 7.2. Sao chép phòng vệ cho collection

Khi dữ liệu là `List`, có thể sao chép để bảo vệ cấu trúc danh sách của record. Ví dụ đầy đủ dưới tên **`ImmutableTagsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ImmutableTagsDemo {
    record Tags(List<String> values) {
        Tags {
            values = List.copyOf(values);
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("java"));
        Tags tags = new Tags(input);

        input.add("record");

        System.out.println("input=" + input);
        System.out.println("record=" + tags.values());
        System.out.println("final=" + java.lang.reflect.Modifier.isFinal(
            Tags.class.getModifiers()
        ));
    }
}
```

```bash
javac --release 17 ImmutableTagsDemo.java
java ImmutableTagsDemo
```

**Stdout:**

```text
input=[java, record]
record=[java]
final=true
```

Trong **compact canonical constructor**, biến tham số `values` được thay bằng bản sao tạo bởi `List.copyOf` trước khi compiler gán vào component field. `List.copyOf` trả danh sách không cho sửa cấu trúc (và từ chối phần tử `null`). Cách này bảo vệ danh sách khỏi việc thay đổi cấu trúc qua tham chiếu `input`, nhưng nếu chính các **phần tử của danh sách là object mutable**, thì tính bất biến sâu vẫn cần biện pháp riêng.

Các chương trình cần bất biến thực sự phải cân nhắc defensive copy, kiểu component phù hợp và hợp đồng `equals/hashCode`. **Không được suy ra điều đó chỉ từ modifier `final` của record.**

## 8. Những quy tắc về phương thức và trạng thái liên quan `java.lang.Record`

Để hiểu tại sao lớp cha chung là `Record` quan trọng, hãy nhớ các thành viên được sinh tại từng record class:

| Thành phần | Nơi tồn tại và quy tắc |
| --- | --- |
| Canonical constructor | Constructor của **record class cụ thể**, ứng với danh sách component trong header; có thể được khai báo/kiểm tra hợp lệ bằng compact constructor. |
| Component fields | Các field `private final` của record class cụ thể, không phải field của `Record`. |
| Accessors | Phương thức `public` tên đúng tên component, như `name()`, `age()`; không mặc định có `getName()`/`getAge()`. |
| `equals(Object)` | `Record` khai báo abstract; compiler sinh implementation cho record class nếu không được viết tường minh. |
| `hashCode()` | `Record` khai báo abstract; compiler sinh implementation tương ứng với components nếu không viết. |
| `toString()` | `Record` khai báo abstract; compiler sinh biểu diễn dựa trên tên record và components nếu không viết. |
| Methods do người viết thêm | Hợp lệ nếu tuân thủ quy tắc record và Java; không tạo thêm instance component field ngoài header. |
| Static members / nested types | Được phép theo quy tắc Java; nested record cũng ngầm định `static`. |

### 8.1. Có thể tự viết `equals/hashCode/toString` không?

**Có**, một record class có thể khai báo các phương thức này tường minh. Nhưng phải giữ các hợp đồng của `Object` và `java.lang.Record`, đặc biệt:

- `equals` phải nhất quán với `hashCode`.
- Hai record cùng loại và có các component tương ứng bằng nhau phải có kết quả `equals` phù hợp với hợp đồng.
- Một record tạo lại từ các giá trị accessor của chính nó phải được xem là bằng bản gốc (**copy invariant** trong Javadoc `java.lang.Record`).
- Không giả định giá trị số cụ thể của `hashCode()` hoặc định dạng chuỗi cụ thể của `toString()` sẽ bất biến qua mọi JDK và phiên bản triển khai; dùng các accessor khi cần dữ liệu có cấu trúc.

Với hầu hết DTO/value carrier đơn giản, nên giữ implementation compiler sinh, trừ khi có yêu cầu miền nghiệp vụ rõ ràng và đã kiểm thử tính nhất quán.

### 8.2. `final` ảnh hưởng tới framework và thiết kế thế nào?

- **Ưu điểm:** Một record không thể bị subclass để thay đổi hình dạng component hoặc override hành vi qua kế thừa lớp. Kiểu dữ liệu công khai dễ hiểu và phù hợp DTO, kết quả xử lý, sự kiện, thông điệp có cấu trúc cố định.
- **Hạn chế:** Cơ chế của một framework dựa trên **tạo subclass/proxy bằng inheritance** không thể áp dụng trực tiếp cho record final. Kiểm tra tài liệu và phiên bản của framework/serializer/ORM đang dùng trước khi dùng record làm entity hoặc đối tượng yêu cầu proxy.
- **Khả năng thay thế:** Thiết kế qua interface, composition, factory hoặc adapter; record có thể implements interface và khai báo phương thức nghiệp vụ thích hợp.

Không dùng quy tắc «record final» để suy luận rằng mọi thư viện JSON, persistence hay dependency injection đều tự hỗ trợ record; khả năng hỗ trợ cụ thể còn phụ thuộc phiên bản và cách tích hợp.

## 9. Các lỗi biên dịch phổ biến

Các đoạn sau **cố ý sai** để nhận diện giới hạn; không ghép chúng vào một file để chạy:

| Cách viết sai | Vì sao sai | Hướng đúng |
| --- | --- | --- |
| `record A(int n) extends Base {}` | Record không có `extends` clause. | Dùng class thường nếu bắt buộc kế thừa Base; hoặc interface nếu chỉ cần hợp đồng. |
| `record A(int n) extends Record {}` | Kể cả superclass bắt buộc cũng không được khai báo tường minh. | Viết `record A(int n) {}`. |
| `class B extends A {}` với `A` là record | Record ngầm định `final`. | Composition hoặc interface. |
| `class B extends java.lang.Record {}` | Chỉ record class mới được kế thừa `java.lang.Record`. | Khai báo bằng `record`. |
| `abstract record A(int n) {}` | Record không được abstract. | Nếu cần kiểu hợp đồng trừu tượng, dùng interface hoặc lớp thường. |
| `sealed record A(int n) {}` | Record không được sealed. | Dùng `sealed interface` được record implements. |
| `record A(int n) { int extra; }` | Không được tự khai báo instance field ngoài components. | Đưa dữ liệu vào record header hoặc tính qua method. |
| `new Record()` | `Record` abstract và constructor không công khai cho ứng dụng. | Khởi tạo record class cụ thể. |
| `Record r = new A(1); r.n();` | Kiểu `Record` không khai báo accessor `n()` của riêng `A`. | Dùng kiểu `A` hoặc interface với method cần gọi. |
| `record` chứa `abstract`/`native` instance method | Record không cho các modifier method này theo JLS. | Dùng implementation Java thông thường. |

**Trường hợp dễ nhầm:** `final record A(int n) {}` lại **hợp lệ**; `final` là dư nhưng không gây lỗi. Không nên dạy rằng «record cấm tất cả modifier liên quan final».

## 10. Quy trình kiểm chứng trên dự án thật

Khi đánh giá một thiết kế dùng record, thực hiện tuần tự:

1. **Xác định vai trò dữ liệu:** Đây là một tập component cố định cần truyền đi, hay là một thực thể có lifecycle/subclass/identity phức tạp?
2. **Xem nhu cầu inheritance:** Nếu phải `extends` class khác, record không phù hợp. Nếu chỉ cần nhiều implementation chung hợp đồng, dùng `implements` interface.
3. **Kiểm tra API thực sự của `Record`:** Đừng giả định `Record` có accessor của mọi record. Dùng concrete type/interface hoặc reflection có kiểm soát.
4. **Kiểm tra tính bất biến:** Các component là primitive, `String`/value type hay mutable array/list/object? Có cần defensive copy/validation không?
5. **Kiểm tra tính tương thích:** Records đã chuẩn hóa từ Java 16; chọn JDK/toolchain còn hỗ trợ sản phẩm. Dùng `javac --release 17` (hoặc release đích đang sử dụng) để xác minh.
6. **Kiểm tra framework:** Liệu proxy, serializer hoặc mapper có đòi constructor rỗng, setter hoặc subclass không? Đối chiếu tài liệu phiên bản thực tế.
7. **Kiểm thử hợp đồng:** Kiểm tra dữ liệu tạo từ canonical constructor, `equals/hashCode`, hành vi accessor, bất biến và test trên runtime đích.

Không cần kiểm tra `final` bằng reflection trong mọi lần sử dụng; ví dụ ở trên chỉ dùng reflection để **xác minh và học cơ chế ngôn ngữ**. Trong mã nghiệp vụ, các bảo đảm đã được compiler áp dụng trực tiếp.

## 11. Tự kiểm tra

**Câu 1.** Với `record Key(String value) {}`, `Key.class.getSuperclass()` trả gì? Có thể tạo `class ExtendedKey extends Key` không?

**Đáp án:** Trả `java.lang.Record`. Không thể extends `Key` vì record class ngầm định final.

**Câu 2.** Có thể viết `record Event(String id) extends java.lang.Record {}` để nêu lớp cha rõ hơn không?

**Đáp án:** Không. Khai báo record không có `extends`; lớp cha trực tiếp `java.lang.Record` được ngôn ngữ ấn định.

**Câu 3.** `java.lang.Record.class.isRecord()` có trả true không? Vì sao?

**Đáp án:** Trả `false`. Đây là abstract base class, không phải một lớp được khai báo bằng `record`. Một record cụ thể như `record Event(String id) {}` mới trả `true` khi gọi `Event.class.isRecord()`.

**Câu 4.** `record User(String name) implements Named {}` có hợp lệ khi `Named` khai báo `String name();` không?

**Đáp án:** Có. Accessor `name()` của record cung cấp implementation phù hợp cho interface. Record là final nhưng vẫn implements interface.

**Câu 5.** Có thể dùng record làm nhánh được phép của một `sealed interface` không?

**Đáp án:** Có. Record final là một loại permitted implementation hợp lệ trong mô hình sealed interface; không cần và cũng không được viết `sealed record`.

**Câu 6.** `record Data(byte[] bytes) {}` có bảo đảm mảng bất biến không?

**Đáp án:** Không. Component field là final nhưng array vẫn mutable; phải đánh giá defensive copy lúc khởi tạo/lúc truy cập và ngữ nghĩa `equals` nếu muốn giá trị bất biến.

**Câu 7.** Vì sao không nên parse chuỗi từ `record.toString()` để lấy component?

**Đáp án:** Javadoc không cam kết giữ nguyên một định dạng chuỗi cụ thể qua mọi implementation/JDK. Lấy giá trị qua accessor hoặc API serialization có hợp đồng định dạng rõ ràng.

## 12. Tài liệu chính thức để đối chiếu

1. [Java Language Specification (Java SE 25) — `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10): `final` ngầm định, modifiers không hợp lệ, superclass `Record`, component, members và constructor.
2. [JLS `8.1.4 Superclasses](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.4): `java.lang.Record` chỉ được kế thừa bởi record class; record không có `extends` clause.
3. [Javadoc Java SE 25 — `java.lang.Record`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html): abstract class, ba phương thức `equals/hashCode/toString`, copy invariant và tính bất biến nông.
4. [Javadoc Java SE 25 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): `isRecord()`, `getRecordComponents()` và `getSuperclass()`.
5. [Oracle Java SE 25 — Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html): ví dụ record, interface, thành viên được phép, reflection và giới hạn kế thừa.
6. [JEP 395 — Records](https://openjdk.org/jeps/395): lịch sử chuẩn hóa record ở Java 16 và cơ sở thiết kế; chỉ dùng bản chính thức cho ứng dụng hiện hành.

**Kết luận kỹ thuật:** Một record là **một lớp cụ thể, final, có superclass trực tiếp `java.lang.Record`**, với các component và accessor ở chính lớp record đó. Nó **không kế thừa lớp tùy ý và không thể bị subclass**, nhưng **có thể implements interface**. `final` bảo vệ cấu trúc lớp và các component field; bất biến sâu của dữ liệu được tham chiếu vẫn do thiết kế chương trình quyết định.