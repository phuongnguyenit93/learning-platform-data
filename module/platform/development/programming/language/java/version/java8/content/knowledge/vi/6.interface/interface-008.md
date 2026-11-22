# Giới hạn đối với phương thức của Object trong Java interface

Interface trong Java mô tả hợp đồng mà lớp triển khai phải hỗ trợ. Từ Java 8, interface có thể cung cấp implementation mặc định bằng phương thức `default`. Tuy vậy, **interface không được dùng `default` để ghi đè (override-equivalent) một phương thức không `private` của `java.lang.Object`**. Đây là giới hạn của ngôn ngữ Java, vẫn còn áp dụng trên các JDK hiện đại.

Ba phương thức thường liên quan nhất là:

- `public String toString()` — biểu diễn đối tượng dưới dạng chuỗi.
- `public boolean equals(Object other)` — xác định quy tắc bằng nhau của hai đối tượng.
- `public int hashCode()` — tính mã băm dùng với các cấu trúc như `HashMap` hoặc `HashSet`.

**Điểm dễ nhầm:** interface **không thể cung cấp `default toString()`, `default equals(Object)`, `default hashCode()`**, nhưng vẫn có thể **khai báo lại các chữ ký `public abstract` tương ứng**. Những khai báo abstract tương đương phương thức public của `Object` cũng **không được tính thành phương thức trừu tượng độc lập** khi xác định một interface có phải functional interface hay không.

Bài này tập trung vào luật của interface, lý do tồn tại giới hạn, cách viết hợp lệ, tương tác với functional interface, hợp đồng `equals`/`hashCode`, trường hợp overload dễ sai và cách thiết kế API đang phù hợp với Java hiện nay.

## 1. Vì sao `Object` đặc biệt đối với interface?

Mọi lớp Java thông thường kế thừa từ `Object` trực tiếp hoặc gián tiếp. Các phương thức public của `Object` là nền tảng chung của các đối tượng:

```java
Object value = new Object();

String representation = value.toString();
boolean sameObject = value.equals(value);
int hash = value.hashCode();
```

Trong hệ thống lớp, implementation của `Object` hoặc implementation override từ một superclass/lớp cụ thể đã xác định hành vi cho các phương thức này. Do đó, khi một lớp `implements` interface, không thể đơn giản coi interface là nơi cung cấp bản `default` thay cho `Object`.

Theo quy tắc JLS về khai báo phương thức của interface:

> Một `default` method có chữ ký *override-equivalent* với một phương thức **không `private`** của `Object` là lỗi biên dịch.

Lệnh cấm này **không chỉ dựa trên tên** mà dựa trên chữ ký theo quy tắc override-equivalent của Java. Ví dụ `equals(Object)` và `equals(String)` **khác danh sách tham số**, nên chúng không cùng chữ ký override. Nhưng việc khai báo overload `equals(String)` dù có thể hợp lệ lại dễ làm người dùng nhầm với `Object.equals(Object)`; xem mục 7.

### 1.1. Phương thức public thường gặp

| Phương thức của `Object` | Chức năng chính | Interface có được cung cấp `default` tương đương? |
| --- | --- | --- |
| `String toString()` | Biểu diễn chuỗi | **Không** |
| `boolean equals(Object obj)` | Kiểm tra bằng nhau | **Không** |
| `int hashCode()` | Giá trị băm | **Không** |

`Object` còn có những phương thức khác với ràng buộc riêng, bao gồm các phương thức `final`. Không cần liệt kê hoặc dùng các API quản lý vòng đời đối tượng lỗi thời để hiểu quy tắc trên. Đặc biệt, việc interface không được khai báo default tương đương `Object` là một **luật ngôn ngữ**, không phải do thiếu annotation hoặc lỗi trong một IDE.

## 2. Những khai báo `default` không hợp lệ

### 2.1. `default toString()`

Ví dụ cố ý **không biên dịch**:

```java
interface TextView {
    // KHÔNG HỢP LỆ nếu bỏ comment:
    // default String toString() {
    //     return "from interface";
    // }
}
```

Lỗi không biến mất khi thêm `@Override` hoặc khai báo lớp triển khai. Nếu bỏ các dấu comment ở trên, compiler phát hiện `default toString()` có chữ ký tương đương `Object.toString()`.

### 2.2. `default equals(Object)`

```java
interface SameValue {
    // KHÔNG HỢP LỆ nếu bỏ comment:
    // default boolean equals(Object other) {
    //     return this == other;
    // }
}
```

Phương thức `Object.equals(Object)` là phương thức instance public. Interface không được đưa implementation mặc định cùng chữ ký vào hợp đồng.

### 2.3. `default hashCode()`

```java
interface HasKey {
    // KHÔNG HỢP LỆ nếu bỏ comment:
    // default int hashCode() {
    //     return 42;
    // }
}
```

Lỗi tương tự với `hashCode()`. Một phương thức hash mặc định trả số cố định không chỉ trái luật khai báo trong interface ở đây mà còn có thể làm suy giảm hiệu quả cấu trúc bảng băm; cách triển khai hash phải bám vào ngữ nghĩa equality của loại đối tượng.

### 2.4. Quy tắc không chỉ nói về ba tên trên

Cần phân biệt hai ý:

1. **Phạm vi luật:** `default` method trong interface không được *override-equivalent* với **bất kỳ phương thức không `private`** nào của `Object`.
2. **Các ví dụ sử dụng thực tế:** `toString`, `equals(Object)` và `hashCode` là các trường hợp phổ biến để học và thiết kế API.

Không suy rộng thành “mọi phương thức có tên `equals` đều bị cấm”. Java xác định overload/override theo **chữ ký**. Ngược lại, không được né luật bằng việc đổi kiểu trả về nhưng giữ tên và tham số: riêng kiểu trả về không tạo một overload hợp lệ.

## 3. Interface vẫn có thể khai báo abstract phương thức của Object

Điểm cốt lõi thứ hai: interface **có thể khai báo công khai, không có thân** những phương thức có chữ ký tương thích với các phương thức public của `Object`:

```java
interface DescribedEntity {
    String name();

    @Override
    String toString();

    @Override
    boolean equals(Object other);

    @Override
    int hashCode();
}
```

Đoạn này là **một interface hợp lệ**. Các khai báo trong interface không ghi `public abstract` nhưng, với phương thức abstract thông thường của interface, các modifier đó được ngầm hiểu. Các annotation `@Override` cũng hợp lệ ở đây: JLS cho phép dùng `@Override` trong interface khi phương thức tương ứng với một phương thức public của `Object`.

Điều đó **không có nghĩa** rằng `DescribedEntity` đã cung cấp implementation cho `toString`, `equals` hay `hashCode`. Nó chỉ tái khai báo chữ ký trong giao diện. Implementation thực tế đến từ `Object`, superclass hoặc lớp triển khai.

### 3.1. Một lớp triển khai có bắt buộc override lại chúng?

Không, **việc khai báo lại abstract `equals(Object)`, `hashCode()` và `toString()` trong interface không tự buộc một lớp concrete phải viết lại tất cả ba phương thức**. Các phương thức public kế thừa từ `Object` đã đáp ứng được chữ ký theo cơ chế của Java.

```java
interface Keyed {
    String key();

    boolean equals(Object other);
    int hashCode();
    String toString();
}

class SimpleKey implements Keyed {
    private final String value;

    SimpleKey(String value) {
        this.value = value;
    }

    @Override
    public String key() {
        return value;
    }
    // Không override equals, hashCode hoặc toString.
}
```

`SimpleKey` là lớp concrete hợp lệ. Nó tiếp tục sử dụng behavior do `Object` cung cấp cho ba phương thức. Theo implementation mặc định của `Object.equals`, hai instance `SimpleKey` khác nhau thường không bằng nhau dù có cùng `value`; chỉ khai báo lại `equals` ở interface **không biến so sánh thành value equality**.

### 3.2. Gọi thông qua biến kiểu interface

```java
Keyed key = new SimpleKey("A");

boolean reflexive = key.equals(key);  // true
int hash = key.hashCode();
String text = key.toString();
```

Cả ba lời gọi đều hợp lệ. Kiểu biến là interface không khiến Java gọi một default implementation từ interface — **không có default như vậy**. Java sử dụng hành vi instance của lớp thực tế hoặc chuỗi superclass theo luật dispatch.

Không nên dựa vào giá trị số `hash` hay định dạng chuỗi của `Object.toString()` để viết test chính xác, vì chúng không phải định dạng nghiệp vụ ổn định. Kiểm tra các hợp đồng liên quan thay vì cố đoán chuỗi đại diện cho đối tượng.

## 4. Ảnh hưởng đến functional interface và lambda

Java định nghĩa functional interface bằng các phương thức trừu tượng thực sự tham gia vào một **single abstract method (SAM)**. Những phương thức abstract có chữ ký tương ứng với phương thức **public instance** của `Object` được bỏ qua khi xét SAM.

Ví dụ quan trọng:

```java
@FunctionalInterface
interface TextProcessor {
    String process(String text);

    boolean equals(Object other);
    int hashCode();
    String toString();
}
```

`TextProcessor` **vẫn là một functional interface** vì `process(String)` là phương thức trừu tượng có ý nghĩa chức năng duy nhất; các khai báo còn lại tương đương với public instance methods của `Object` không tính là các SAM bổ sung.

Do đó:

```java
TextProcessor trim = String::trim;
String result = trim.process("  Java  "); // "Java"
```

Đoạn dùng method reference Java 8 có thể biên dịch trong ngữ cảnh có `TextProcessor`. Lambda cũng hợp lệ:

```java
TextProcessor upper =
        text -> text.toUpperCase(java.util.Locale.ROOT);
```

Không cần tạo thêm interface khác chỉ vì muốn đề cập `equals`/`hashCode`/`toString`. Tuy nhiên, với một API đơn thuần biến đổi chuỗi, `Function<String,String>` chuẩn có thể đủ; không phải interface nào cũng nên tự khai báo thêm ba phương thức `Object`.

### 4.1. Nếu chỉ khai báo phương thức Object thì không phải functional interface

```java
// KHÔNG HỢP LỆ khi dùng @FunctionalInterface:
@FunctionalInterface
interface OnlyObjectMethods {
    boolean equals(Object other);
    int hashCode();
    String toString();
}
```

Ở đây **không có** phương thức abstract độc lập để làm SAM, nên annotation `@FunctionalInterface` gây lỗi biên dịch. Nếu bỏ annotation, `OnlyObjectMethods` có thể là một interface Java thông thường, nhưng vẫn **không có target SAM phù hợp để gán lambda**.

Tránh nhầm “được phép khai báo abstract phương thức Object” với “những khai báo đó tự động tạo functional interface”.

### 4.2. Phân biệt `equals(Object)` và `equals(String)` trong SAM

`boolean equals(String other)` **không override** `Object.equals(Object)` vì tham số khác nhau. Nếu interface khai báo nó, nó có thể là **một phương thức trừu tượng mới**:

```java
@FunctionalInterface
interface StringMatcher {
    boolean equals(String other);
}
```

Đây là ví dụ cú pháp có thể hợp lệ nhưng **không được khuyến nghị trong thiết kế API**: tên `equals` dễ khiến người dùng nghĩ tới hợp đồng equality của `Object`, trong khi đây là một overload nhận `String`.

Một tên rõ hơn là:

```java
@FunctionalInterface
interface StringMatcher {
    boolean matches(String other);
}
```

Hãy chọn tên phản ánh ý định nghiệp vụ, đồng thời tránh overload gây bẫy khi phân giải phương thức.

## 5. Cách thiết kế đúng khi muốn một mô tả mặc định

Nhu cầu thật: “mọi đối tượng triển khai interface phải có một chuỗi mô tả nhất quán”. Ta **không thể** viết `default String toString()` trong interface. Nhưng có thể cung cấp một default method **khác chữ ký của `Object`**, rồi để lớp quyết định cách sử dụng.

```java
interface Displayable {
    String code();

    default String description() {
        return "code=" + code();
    }
}

class Product implements Displayable {
    private final String code;

    Product(String code) {
        this.code = code;
    }

    @Override
    public String code() {
        return code;
    }

    @Override
    public String toString() {
        return "Product[" + description() + "]";
    }
}
```

`Displayable.description()` là default method hợp lệ: tên này không trùng một phương thức không `private` tương ứng của `Object`. `Product.toString()` là phương thức **lớp** và được override hợp lệ.

```java
Product p = new Product("P01");

System.out.println(p.description()); // code=P01
System.out.println(p);               // Product[code=P01]
```

Ý tưởng ở đây là **chia trách nhiệm đúng chỗ**: interface cung cấp logic dùng chung khi có ý nghĩa, lớp triển khai chịu trách nhiệm trình bày `toString` cuối cùng. Nếu không muốn bắt tất cả implementation override `toString`, người gọi có thể sử dụng trực tiếp `description()` như một phần API.

### 5.1. Có cần khai báo `toString()` abstract trên interface?

Không nhất thiết. Tái khai báo:

```java
interface Displayable {
    String code();

    String toString();
}
```

là hợp lệ, nhưng không đảm bảo lớp triển khai có bản `toString` mang ý nghĩa nghiệp vụ: implementation mặc định từ `Object` vẫn đáp ứng chữ ký. Nếu muốn một chuỗi mô tả thực sự được ứng dụng định nghĩa, hãy tạo phương thức riêng như `displayText()`, `description()` hoặc `label()` và kiểm thử hợp đồng của nó.

### 5.2. Nếu muốn định nghĩa equality theo giá trị

Không thể dùng default method trong interface để áp đặt `equals(Object)` hoặc `hashCode()`. Thay vào đó, có thể:

- Viết `equals`/`hashCode` ở **lớp concrete**, sử dụng cùng những trường tạo nên identity/value semantics.
- Đặt logic chung trong một phương thức tên khác nếu có ích, nhưng lớp vẫn phải override hai phương thức `Object` theo một hợp đồng nhất quán.
- Với **kiểu dữ liệu giá trị** trên Java 16+, cân nhắc `record` khi đặc tính tự tạo `equals`, `hashCode` và `toString` theo các component của record phù hợp nhu cầu. `record` không có ở Java 8; đây là lựa chọn hiện đại có giới hạn phiên bản rõ ràng.
- Xác định xem hệ thống muốn **reference identity** hay **value equality**: không phải mọi đối tượng đều cần override `equals`.

Chỉ thay `equals` mà bỏ `hashCode` thường làm hỏng các cấu trúc băm. Đừng thiết kế interface tưởng như tự sửa được chuyện này bằng khai báo abstract phương thức của `Object`.

## 6. Hợp đồng `equals` và `hashCode` vẫn do Object quy định

Đây là lý do thực tế khiến việc override hai phương thức ở lớp phải được xem là một quyết định thiết kế nghiêm túc.

### 6.1. Quy tắc quan trọng của `equals(Object)`

Với đối tượng không null và khi so sánh trong cùng trạng thái ổn định:

1. **Reflexive:** `x.equals(x)` phải là `true`.
2. **Symmetric:** `x.equals(y)` có kết quả giống `y.equals(x)`.
3. **Transitive:** nếu `x.equals(y)` và `y.equals(z)` đều đúng, thì `x.equals(z)` cũng phải đúng.
4. **Consistent:** khi thông tin dùng để so sánh không thay đổi, kết quả các lần gọi nên nhất quán.
5. **Non-null:** `x.equals(null)` phải là `false`.

Với dữ liệu giá trị, chỉ nên so sánh các trường thuộc định nghĩa equality. Không lấy thông tin biến động không liên quan làm thành phần so sánh một cách tùy tiện.

### 6.2. Quy tắc quan trọng của `hashCode()`

- Nếu `x.equals(y)` là `true`, thì `x.hashCode() == y.hashCode()` **phải đúng**.
- Hai đối tượng không bằng nhau **vẫn có thể** trùng hash code; hash collision không tự động có nghĩa là hai đối tượng bằng nhau.
- Hash code nên ổn định khi các thuộc tính tham gia equality không đổi, đặc biệt khi đối tượng đang làm khóa trong `HashMap` hoặc phần tử của `HashSet`.

Ví dụ một lớp giá trị nhỏ:

```java
import java.util.Objects;

final class CustomerId {
    private final String value;

    CustomerId(String value) {
        this.value = Objects.requireNonNull(value);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof CustomerId)) {
            return false;
        }
        CustomerId that = (CustomerId) other;
        return value.equals(that.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }

    @Override
    public String toString() {
        return "CustomerId[" + value + "]";
    }
}
```

Đây là **định nghĩa lớp minh họa**, không phải chương trình có `main`. Nó tương thích Java 8+. `CustomerId` là `final` và `value` là `final`, giúp giữ equality ổn định theo giá trị `String` không đổi. Có thể dùng `Objects.hash(value)`, nhưng khi chỉ có một `String` thì `value.hashCode()` thể hiện đủ quy tắc và tránh một số chi phí không cần thiết.

### 6.3. Hệ quả với `HashSet` và `HashMap`

Với hai `CustomerId("A")` riêng biệt:

```java
CustomerId a = new CustomerId("A");
CustomerId b = new CustomerId("A");

boolean equal = a.equals(b); // true
boolean equalHash = a.hashCode() == b.hashCode(); // true
```

`HashSet` sẽ coi `a` và `b` là phần tử trùng nhau theo `equals`/`hashCode`. Nếu không override đúng hai phương thức, các đối tượng giá trị trông giống nhau có thể được tính là các phần tử khác nhau; điều đó có thể đúng hoặc sai tùy mô hình nghiệp vụ.

Không thay đổi các trường dùng trong `hashCode` của một đối tượng sau khi đưa nó vào collection băm. Nếu cần object mutable, thiết kế key bất biến riêng thường an toàn hơn.

## 7. Lỗi dễ mắc: overload `equals` thay vì override

Giả sử lập trình viên viết:

```java
class BadCustomerId {
    private final String value;

    BadCustomerId(String value) {
        this.value = value;
    }

    public boolean equals(BadCustomerId other) {
        return other != null && value.equals(other.value);
    }
}
```

Phương thức `equals(BadCustomerId)` **không override `equals(Object)`**. Nó là overload mới. Khi so sánh qua biến kiểu `Object` hoặc khi collection gọi `equals(Object)`, Java vẫn dùng implementation khác (mặc định của `Object` trong trường hợp này).

```java
BadCustomerId a = new BadCustomerId("A");
BadCustomerId b = new BadCustomerId("A");

boolean direct = a.equals(b);          // true (gọi overload)
boolean throughObject = ((Object) a)
        .equals(b);                    // false (gọi Object.equals)
```

Đây là ví dụ minh họa cụ thể vì sao chỉ nhìn `a.equals(b)` có thể che một lỗi thiết kế value equality. Một cách phòng lỗi:

```java
@Override
public boolean equals(Object other) {
    // So sánh với đúng hợp đồng của Object.
}
```

Annotation `@Override` sẽ làm compiler báo lỗi nếu bạn vô tình dùng `equals(BadCustomerId)` khi nghĩ mình đang override `Object.equals`. Cũng cần override `hashCode()` nhất quán.

**Quy tắc liên quan tới interface:** một default overload `equals(SomeType)` có thể không trùng chữ ký `Object.equals(Object)`, nhưng đặt tên như vậy dễ làm tăng nhầm lẫn. Nên dùng tên nghiệp vụ như `sameAccountAs`, `matchesCode`, `hasSameValue` khi không có ý định override chính xác `equals(Object)`.

## 8. `@Override` trên interface và trên lớp có ý nghĩa gì?

### 8.1. Interface dùng `@Override` với abstract `Object` method

```java
interface PublicObjectContracts {
    @Override
    boolean equals(Object value);

    @Override
    int hashCode();

    @Override
    String toString();
}
```

Các khai báo này hợp lệ theo JLS. Chúng không phải default implementation. Chúng cũng không đồng nghĩa rằng interface này là functional interface; không có phương thức abstract **khác** `Object` để đóng vai trò SAM.

### 8.2. Lớp dùng `@Override` khi triển khai hành vi

```java
final class ProductCode {
    private final String value;

    ProductCode(String value) {
        this.value = value;
    }

    @Override
    public String toString() {
        return "ProductCode(" + value + ")";
    }
}
```

Đây là nơi hợp lệ để tùy biến `toString`, vì lớp có thể override implementation kế thừa từ `Object`. Nếu một interface có default method tên `description()`, lớp còn có thể gọi nó bên trong `toString()`.

Không thể thay một phương thức `Object` bằng `private` hoặc `static` cùng chữ ký ở lớp theo ý muốn: quy tắc override/hiding và mức truy cập của Java vẫn phải thỏa mãn.

## 9. Chương trình Java hoàn chỉnh và stdout xác định

Chương trình sau minh họa đồng thời các điểm:

- Interface được khai báo abstract `toString`, `equals`, `hashCode` nhưng không cung cấp default.
- Functional interface có SAM thực sự vẫn dùng được lambda/method reference dù chứa những khai báo abstract tương ứng với `Object`.
- Lớp có thể dùng default method với **tên riêng** để tạo mô tả, sau đó override `toString` ở cấp lớp.
- Một lớp khác không override các phương thức `Object` vẫn hợp lệ nhưng giữ reference equality mặc định.
- Lớp giá trị override `equals`/`hashCode` nhất quán, nên `HashSet` nhận diện hai giá trị bằng nhau.

Tạo file **`ObjectMethodLimitsDemo.java`**:

```java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ObjectMethodLimitsDemo {

    @FunctionalInterface
    interface TextProcessor {
        String process(String text);
        boolean equals(Object other);
        int hashCode();
        String toString();
    }

    interface Described {
        String code();

        String toString();

        default String description() {
            return "code=" + code();
        }
    }

    static final class Item implements Described {
        private final String code;

        Item(String code) {
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public String code() {
            return code;
        }

        @Override
        public String toString() {
            return "Item[" + description() + "]";
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Item)) {
                return false;
            }
            Item that = (Item) other;
            return code.equals(that.code);
        }

        @Override
        public int hashCode() {
            return code.hashCode();
        }
    }

    static final class Basic implements Described {
        private final String code;

        Basic(String code) {
            this.code = code;
        }

        @Override
        public String code() {
            return code;
        }

        // Object.toString() và Object.equals(Object) vẫn được kế thừa.
    }

    public static void main(String[] args) {
        TextProcessor trim = String::trim;
        System.out.println("Process: "
                + trim.process("  Java  "));
        System.out.println("Self equal: " + trim.equals(trim));

        Item first = new Item("A");
        Item sameValue = new Item("A");
        Item different = new Item("B");

        System.out.println("Description: " + first.description());
        System.out.println("toString: " + first.toString());
        System.out.println("Value equal: " + first.equals(sameValue));
        System.out.println("Different: " + first.equals(different));
        System.out.println("Same hash: "
                + (first.hashCode() == sameValue.hashCode()));

        Set<Item> unique = new HashSet<>();
        unique.add(first);
        unique.add(sameValue);
        unique.add(different);
        System.out.println("HashSet size: " + unique.size());

        Described view = first;
        System.out.println("Interface view: " + view.toString());

        Basic left = new Basic("A");
        Basic right = new Basic("A");
        System.out.println("Object identity: " + left.equals(right));
        System.out.println("Object self: " + left.equals(left));
    }
}
```

Lệnh chạy (JDK 17+; mã chỉ dùng cú pháp/API tương thích Java 8):

```bash
javac ObjectMethodLimitsDemo.java
java ObjectMethodLimitsDemo
```

**Stdout chính xác:**

```text
Process: Java
Self equal: true
Description: code=A
toString: Item[code=A]
Value equal: true
Different: false
Same hash: true
HashSet size: 2
Interface view: Item[code=A]
Object identity: false
Object self: true
```

Giải thích:

1. `TextProcessor` là functional interface thật: `process` là SAM, còn các chữ ký public `Object` không được tính thêm. `String::trim` cung cấp implementation cho `process`, trả `Java`.
2. `trim.equals(trim)` có kết quả `true` theo hợp đồng reflexive của `equals` trên đối tượng không null. Không in `trim.toString()` vì representation cụ thể của đối tượng lambda không phải định dạng nghiệp vụ ổn định.
3. `Item` triển khai `description()` bằng default của interface nhưng **lớp tự override `toString()`** để in `Item[code=A]`.
4. Hai `Item` có code `"A"` bằng nhau theo `equals` và tạo cùng `hashCode`. `Item("B")` khác, nên `HashSet` chỉ chứa hai giá trị riêng biệt.
5. Biến `view` kiểu `Described` vẫn gọi implementation `Item.toString()`. Ép kiểu hay sử dụng interface không làm thay đổi nơi implementation đến từ.
6. Hai `Basic` khác object dù cùng `code`, nên `Object.equals` theo reference identity cho `false`; tự so sánh cùng object cho `true`.

Ví dụ cố ý không in giá trị hash code cụ thể hoặc chuỗi mặc định `Object.toString`, vì những chi tiết này không nên trở thành giả định trong chương trình.

## 10. Tương tác với `record`, interface và Java hiện đại

Kể từ **Java 16**, `record` là một lựa chọn ổn định cho một số kiểu dữ liệu dạng giá trị. Record tự cung cấp các phương thức `equals`, `hashCode` và `toString` dựa trên component của record, đồng thời có thể triển khai interface.

```java
interface HasCode {
    String code();

    default String description() {
        return "code=" + code();
    }
}

// Java 16+
record ProductCode(String code) implements HasCode {
}
```

Đoạn này là minh họa dùng record **Java 16+**, không tương thích cú pháp với Java 8. `ProductCode` có accessor `code()` đáp ứng `HasCode.code()`, đồng thời có `Object` methods được sinh tự động theo quy tắc record.

Nếu muốn quy tắc hiển thị không phụ thuộc định dạng `toString` do compiler sinh, người dùng API vẫn có thể gọi `description()`. Với dự án phải biên dịch ở mức Java 8, dùng một lớp bất biến thông thường và override các phương thức theo hợp đồng. Không sử dụng record trong chương trình Java 8-compatible ở mục 9.

## 11. Checklist thiết kế interface liên quan Object

| Câu hỏi | Cách xử lý phù hợp |
| --- | --- |
| Muốn viết `default String toString()` trong interface? | **Không**; dùng tên default method khác hoặc override tại lớp |
| Muốn viết `default boolean equals(Object)`? | **Không**; đặt quy tắc equality ở lớp/kiểu giá trị |
| Muốn viết `default int hashCode()`? | **Không**; hash phải đi cùng equality ở lớp |
| Muốn interface chỉ tuyên bố `String toString()`? | Được, nếu là khai báo abstract hợp lệ; không cung cấp phần thân |
| Có cần tự viết `toString` ở mỗi lớp implements? | Không bắt buộc, vì `Object` cung cấp implementation; nhưng có thể cần để đáp ứng ý nghĩa nghiệp vụ |
| Interface có `apply(T)` và khai báo thêm abstract `equals/hashCode/toString`? | Vẫn có thể là functional interface vì các chữ ký public `Object` không được tính vào SAM |
| Interface chỉ khai báo lại `equals/hashCode/toString`? | Không tạo ra SAM đủ để gán lambda |
| Một lớp muốn so sánh bằng giá trị? | Override `equals(Object)` và `hashCode()` nhất quán; cân nhắc kiểu dữ liệu bất biến |
| Một lớp chỉ viết `equals(MyType)`? | Đó là overload, không override `Object.equals(Object)` |
| Muốn mô tả mặc định dùng chung? | Tạo `default description()` hoặc tên khác, và để lớp quyết định `toString()` |
| Dự án dùng Java 16+ và cần value carrier đơn giản? | Cân nhắc `record` nếu phù hợp; không dùng cho source level Java 8 |

### Những lỗi cần tránh

1. **Cố “đánh lừa” compiler bằng annotation:** `@Override` không khiến default `Object` method trong interface trở thành hợp lệ.
2. **Dùng cùng tên nhưng đổi kiểu trả về để né quy tắc:** kiểu trả về không tự tạo overload hợp lệ.
3. **Hiểu rằng abstract equals/hashCode/toString trong interface bắt buộc lớp viết lại:** `Object` vốn đã cung cấp các phương thức public.
4. **Nghĩ abstract phương thức Object làm functional interface có thêm SAM:** các phương thức tương ứng với public instance `Object` bị loại khỏi phép tính SAM.
5. **Ghi `equals(MyClass)` rồi tưởng đã override `equals(Object)`:** kiểm tra bằng `@Override`.
6. **Chỉ override `equals` nhưng bỏ `hashCode`:** có nguy cơ phá hợp đồng của collection dựa trên hash.
7. **Cho rằng hash khác thì mới biết object khác:** hai object không bằng nhau vẫn có thể trùng hash code.
8. **Dùng `Object.toString()` làm định dạng dữ liệu dài hạn:** không thích hợp để làm khóa lưu trữ, định dạng API công khai hoặc output test kỳ vọng cụ thể.
9. **Dùng interface để áp đặt value equality mà không kiểm thử implementation:** một khai báo abstract `equals` không tự quy định các trường cần so sánh.
10. **Nhầm phiên bản:** `default method` và lambda từ Java 8; `record` từ Java 16. Chỉ chọn tính năng phù hợp JDK/source level dự án.

## 12. Tóm tắt quy tắc

- **Cấm:** interface có `default` method mang chữ ký *override-equivalent* với một phương thức **không `private`** của `Object`.
- **Cho phép:** interface tái khai báo abstract những public instance methods hợp lệ của `Object`, ví dụ `String toString()`, `boolean equals(Object)`, `int hashCode()`.
- **Functional interface:** những khai báo abstract tương đương public instance `Object` không tạo thêm SAM; interface cần **một phương thức chức năng trừu tượng thực sự**.
- **Triển khai:** behavior của `Object` hoặc override từ superclass/lớp concrete được sử dụng; interface có thể đưa ra một default helper **với tên/chữ ký khác**, còn lớp tự quyết định `toString`/`equals`/`hashCode`.
- **Thiết kế:** nếu override equality, giữ đúng hợp đồng `equals`/`hashCode` và ưu tiên đối tượng key bất biến.

Đây là các quy tắc ngôn ngữ và API **vẫn còn hiệu lực trong Java hiện đại**, không cần dựa vào kỹ thuật lỗi thời.

## Tài liệu chuẩn để tra cứu

- Java Language Specification, chương 9 **Interfaces**, `9.4.1.2 *Requirements in Overriding* (lệnh cấm default tương đương phương thức không private của Object): https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4.1.2
- Java Language Specification, `9.8 *Functional Interfaces* (phương thức tương đương public Object không tính vào SAM): https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.8
- Java Language Specification, `9.2 *Interface Members*: https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.2
- Java SE API, `java.lang.Object`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html
