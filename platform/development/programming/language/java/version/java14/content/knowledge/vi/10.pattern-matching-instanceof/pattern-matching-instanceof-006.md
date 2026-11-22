# Quan hệ của mẫu `instanceof` với kế thừa, interface và phép ép kiểu (Java 17+)

## 1. Bức tranh tổng quan

**Pattern matching for `instanceof`** cho phép một biểu thức vừa **kiểm tra kiểu thực tế của đối tượng** vừa **đặt tên biến đã có kiểu phù hợp**, thay vì kiểm tra xong rồi ép kiểu thủ công. Tính năng được giới thiệu dưới dạng preview ở Java 14, nhưng đã **chính thức từ Java 16 (JEP 394)** và tiếp tục được hỗ trợ trong Java hiện đại.

Cú pháp cốt lõi:

```java
Object value = "Hello";

if (value instanceof String text) {
    System.out.println(text.toUpperCase()); // HELLO
}
```

Trong `value instanceof String text`:

1. `value` là biểu thức chứa tham chiếu đối tượng đang kiểm tra.
2. `String` là **kiểu đích** của *type pattern*.
3. `text` là **pattern variable** kiểu `String`. Biến này chỉ được khởi tạo và dùng ở nơi trình biên dịch chứng minh phép khớp thành công.
4. Với đối tượng không phải `String`, hoặc `value == null`, phép kiểm tra trả `false` và không có `text` hợp lệ để dùng ở nhánh thất bại.

Mẫu `instanceof` thường được dùng khi biến ban đầu có kiểu **lớp cha, interface hoặc `Object`**, còn một nhánh xử lý cần dùng API riêng của **lớp con hoặc lớp triển khai interface**.

**Phạm vi bài học:** type pattern ổn định trong `instanceof` và mối quan hệ với hệ thống kiểu Java, nhất là Java 17+. Bài dùng cú pháp đã chính thức, không dùng primitive patterns đang ở chế độ preview hay dựa vào cú pháp preview của Java 14.

## 2. Kế thừa quyết định vì sao mẫu có thể khớp

Giả sử có hệ phân cấp:

```java
interface Named {
    String name();
}

abstract class Animal implements Named {
    private final String name;

    protected Animal(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }
}

final class Dog extends Animal {
    private final String breed;

    Dog(String name, String breed) {
        super(name);
        this.breed = breed;
    }

    String breed() {
        return breed;
    }
}

final class Cat extends Animal {
    Cat(String name) {
        super(name);
    }
}
```

Đoạn trên là **các khai báo kiểu minh họa**; để chạy độc lập, sử dụng chương trình hoàn chỉnh ở mục 9.

Quan hệ:

- `Dog extends Animal` và `Cat extends Animal`: `Dog` và `Cat` là **subtype** của `Animal`.
- `Animal implements Named`: mọi instance `Dog`/`Cat` cũng đáp ứng interface `Named` theo quan hệ kế thừa.
- `Dog` có phương thức `breed()` mà kiểu cha `Animal` và interface `Named` **không khai báo**.

Vì vậy, với một tham chiếu kiểu cha:

```java
Animal animal = new Dog("Milo", "Beagle");

System.out.println(animal.name()); // Milo (method có trên Animal)
if (animal instanceof Dog dog) {
    System.out.println(dog.breed()); // Beagle (method của Dog)
}
```

**Điểm then chốt:** kiểu tĩnh của biến `animal` là `Animal`, nhưng đối tượng tại runtime là một `Dog`. Phép `instanceof Dog dog` kiểm tra **đối tượng thực tế**, không chỉ nhìn kiểu khai báo của biến. Nếu nhánh khớp, `dog` có kiểu tĩnh `Dog` để gọi `breed()`.

Nếu `animal` là `new Cat("Nora")` thì `animal instanceof Dog dog` trả `false`. Không có chuyển đổi nào biến một `Cat` thành `Dog`.

### 2.1. Kiểm tra cả lớp cha và lớp con

```java
Object obj = new Dog("Milo", "Beagle");

System.out.println(obj instanceof Animal); // true
System.out.println(obj instanceof Dog);    // true
System.out.println(obj instanceof Named);  // true
System.out.println(obj instanceof Cat);    // false
```

Đây là ví dụ trong cùng phạm vi có các khai báo lớp ở trên. Một object `Dog` thỏa nhiều kiểu **cùng lúc**: bản thân `Dog`, lớp cha `Animal`, interface `Named` và `Object`. `instanceof` kiểm tra tính tương thích với **kiểu đích** trên object đó.

### 2.2. Vì sao thứ tự kiểm tra ảnh hưởng xử lý

Với chuỗi:

```java
if (obj instanceof Animal animal) {
    System.out.println(animal.name());
} else if (obj instanceof Dog dog) {
    System.out.println(dog.breed());
}
```

Nhánh `Dog` **không bao giờ được thực thi** cho một object `Dog`, vì object đó đã khớp nhánh rộng `Animal` ở đầu. Với những nhánh yêu cầu hành vi đặc thù, kiểm tra **kiểu cụ thể trước** kiểu rộng hơn:

```java
if (obj instanceof Dog dog) {
    System.out.println(dog.breed());
} else if (obj instanceof Animal animal) {
    System.out.println(animal.name());
}
```

Với cùng một object `Dog`, phiên bản sau đi vào nhánh `Dog`. Đây là hệ quả của `if/else if` chạy theo thứ tự, **không phải** một cơ chế tự chọn “mẫu cụ thể nhất”.

## 3. `interface` và `record implements interface`

Interface mô tả **hợp đồng**, còn object có thể thuộc bất kỳ lớp triển khai tương ứng. Nếu biến có kiểu `Named`:

```java
Named value = new Dog("Milo", "Beagle");
System.out.println(value.name()); // Milo

if (value instanceof Dog dog) {
    System.out.println(dog.breed()); // Beagle
}
```

Chương trình gọi `name()` qua interface bằng **đa hình**. Pattern cần thiết chỉ khi muốn truy cập chi tiết riêng của `Dog`, ví dụ `breed()`.

Một `record` cũng có thể **implements interface**:

```java
interface Named {
    String name();
}

record Badge(String name, int level) implements Named {}
```

Accessor `name()` do record sinh tự động là `public String name()`, nên đáp ứng `Named.name()`. Record là class ngầm định `final` và không thể `extends Animal`, nhưng **có thể triển khai interface**:

```java
Named item = new Badge("STAFF", 3);

System.out.println(item.name()); // STAFF

if (item instanceof Badge badge) {
    System.out.println(badge.level()); // 3
}
```

**Bảng lựa chọn theo kiểu tĩnh:**

| Kiểu của tham chiếu | Đối tượng thực tế | Mẫu kiểm tra | Kết quả |
| --- | --- | --- | --- |
| `Object` | `new Dog(...)` | `instanceof Dog dog` | Khớp |
| `Animal` | `new Dog(...)` | `instanceof Dog dog` | Khớp |
| `Named` | `new Dog(...)` | `instanceof Animal animal` | Khớp |
| `Named` | `new Badge(...)` | `instanceof Badge badge` | Khớp |
| `Named` | `new Badge(...)` | `instanceof Dog dog` | Không khớp |
| `Object` | `null` | `instanceof Named named` | Không khớp |

Nếu mã chỉ cần `name()`, hãy gọi **`item.name()` trên interface `Named`** thay vì liên tục phân loại `Dog`, `Cat` và `Badge`. Pattern matching phù hợp khi thực sự cần nhánh xử lý riêng hoặc kiểm tra dữ liệu từ nguồn không đồng nhất.

## 4. Mẫu `instanceof` và ép kiểu: giống và khác

### 4.1. Cách truyền thống: kiểm tra rồi ép kiểu tường minh

```java
static String oldStyle(Object input) {
    if (input instanceof Dog) {
        Dog dog = (Dog) input; // Cast tường minh sau kiểm tra
        return dog.breed();
    }
    return "not dog";
}
```

Đây là **phương thức minh họa đặt trong class có kiểu `Dog`**. Đoạn mã vẫn hợp lệ trong Java hiện đại; nó chỉ dài hơn và dễ xảy ra lỗi khi kiểm tra một kiểu nhưng lại ép sang kiểu khác.

### 4.2. Cách dùng pattern: kiểm tra và lấy biến một lần

```java
static String withPattern(Object input) {
    if (input instanceof Dog dog) {
        return dog.breed(); // dog đã có kiểu Dog
    }
    return "not dog";
}
```

Kết quả nghiệp vụ tương đương: `dog` là tham chiếu đến **chính object đã được kiểm tra**. Java không tạo thêm một instance `Dog` hoặc gọi constructor mới. Pattern giúp giảm việc lặp tên kiểu và hạn chế việc kiểm tra/cast thiếu nhất quán.

### 4.3. Ép kiểu trực tiếp có thể ném `ClassCastException`

```java
Object obj = new Dog("Milo", "Beagle");

// Nếu bỏ kiểm tra và ép kiểu sai:
String name = (String) obj; // ClassCastException tại runtime
```

Đoạn trên **cố ý gây lỗi khi chạy**, vì kiểu tĩnh `Object` cho phép cast sang `String`, nhưng đối tượng thực tế là `Dog`. Mẫu `if (obj instanceof String s)` sẽ trả `false` thay vì ép kiểu sai.

Phân biệt:

- **`instanceof` (type pattern):** kiểm tra quan hệ kiểu tại runtime; nếu không khớp, trả `false` và không cấp biến pattern.
- **Cast `(T) expr`:** biểu thức chuyển đổi kiểu có thể thành công hoặc ném `ClassCastException` nếu runtime không tương thích.
- **Upcast:** `Dog dog = ...; Animal a = dog;` hoặc `Named n = dog;` thường thực hiện ngầm định, không cần `instanceof` hay cast tường minh.
- **Downcast:** từ `Animal`/`Named`/`Object` về `Dog` đòi hỏi kiểm tra khả năng tương thích; type pattern thường là cách rõ ràng khi cần dùng API riêng của `Dog`.

**Không nên dùng `instanceof` chỉ để kiểm tra rồi cast sang cùng kiểu đó thêm một lần**; biến pattern đã mang kiểu đích.

### 4.4. Đa hình làm giảm nhu cầu ép kiểu

Nếu có:

```java
static String showName(Named value) {
    return value.name();
}
```

thì `showName(new Dog("Milo", "Beagle"))` và `showName(new Badge("STAFF", 3))` đều dùng được mà **không cần pattern**. Method được gọi theo hợp đồng của interface và triển khai của object. Khi thiết kế API, hãy ưu tiên các method chung của class cha/interface; dùng pattern khi luồng xử lý thật sự phụ thuộc vào subtype.

## 5. Phạm vi biến mẫu (*flow scoping*)

Một pattern variable chỉ được sử dụng ở nơi compiler chứng minh mẫu **đã khớp**. Đây là **flow scoping**, khác với việc chỉ quan sát dấu ngoặc nhọn.

### 5.1. `if` và toán tử `&&`

```java
static boolean isLongText(Object value) {
    if (value instanceof String text && text.length() >= 5) {
        return true;
    }
    return false;
}
```

Ở phần bên phải của `&&`, `text` đã hợp lệ vì điều kiện bên trái phải `true` thì Java mới đánh giá phần bên phải (**short-circuit AND**). Mẫu `instanceof String text` vừa bảo đảm kiểu `String`, vừa tránh phải ép kiểu để gọi `length()`.

### 5.2. Phủ định và return sớm

```java
static String upperOrFallback(Object input) {
    if (!(input instanceof String text)) {
        return "not string";
    }
    return text.toUpperCase(java.util.Locale.ROOT);
}
```

Dòng `return text...` phía sau `if` hợp lệ vì đường chạy còn tiếp tục chỉ khi phép kiểm tra `instanceof String` thành công. Biến `text` vẫn nằm trong phạm vi chắc chắn đã khớp.

Ví dụ này cũng cho thấy khi `input == null`, kết quả là `"not string"`; pattern không khớp `null`.

### 5.3. `||` không bảo đảm pattern đã khớp

```java
// CỐ Ý SAI — minh họa lỗi biên dịch:
static boolean invalid(Object value) {
    return value instanceof String text || text.isEmpty();
}
```

Nhánh bên phải `||` có thể chạy **khi bên trái false**, nên `text` không được bảo đảm đã gán. `javac` có thể báo `cannot find symbol: variable text`. Không sửa bằng cách ép kiểu vào vị trí đó; hãy viết điều kiện phù hợp, chẳng hạn:

```java
static boolean valid(Object value) {
    return value instanceof String text && !text.isEmpty();
}
```

Công thức đúng phụ thuộc mục đích nghiệp vụ. `&&` ở ví dụ sau có ý nghĩa “đúng là String và không rỗng”, không phải phép thay thế máy móc cho mọi biểu thức `||`.

### 5.4. Biến pattern không mặc định tồn tại trong `else`

```java
if (obj instanceof Dog dog) {
    System.out.println(dog.breed()); // dog hợp lệ
} else {
    System.out.println("Not a dog");
    // dog.breed(); // SAI: không có dog đã khớp trong nhánh else
}
```

Hai nhánh `if` khác nhau có thể khai báo pattern variables cùng tên ở những phạm vi không chồng lấn, nhưng nên dùng tên rõ nghĩa để tránh nhầm.

## 6. Tương thích kiểu ở thời điểm biên dịch

`instanceof` **không** phải phép thử tùy ý giữa mọi cặp kiểu. Compiler phải xác định phép kiểm tra/cast có thể hợp lệ theo quan hệ kiểu Java và những giới hạn của ngôn ngữ.

Ví dụ lớp final không liên quan:

```java
// CỐ Ý SAI:
static boolean impossible(String text) {
    return text instanceof Integer number;
}
```

`String` và `Integer` đều là final class không có quan hệ subtype phù hợp; compiler biết giá trị có kiểu tĩnh `String` không thể là `Integer`. Lỗi xảy ra **lúc biên dịch**, không phải trả `false` tại runtime.

Ngược lại, khi biểu thức có kiểu tĩnh `Object` hoặc interface đủ rộng, có thể có nhiều kiểu triển khai thực tế:

```java
static boolean isInteger(Object value) {
    return value instanceof Integer number && number > 0;
}
```

Điều này hợp lệ: một `Object` có thể tham chiếu đến instance `Integer`. Pattern variable `number` có kiểu `Integer`, nên `number > 0` có thể unbox để so sánh số học.

### 6.1. Cẩn thận với mẫu luôn khớp và phiên bản source

Quy tắc của kiểu mẫu có một điểm khác biệt theo phiên bản Java:

```java
// Ví dụ minh họa, không đặt vào chương trình Java 17 ở mục 9:
String text = "hello";
if (text instanceof String same) {
    System.out.println(same);
}
```

- Với **`javac --release 17`**, trường hợp kiểu tĩnh `String` đã là subtype của kiểu mẫu `String` bị compiler từ chối; nó xem đây là kiểm tra mẫu không cần thiết.
- Với **`javac --release 21`** (và các phiên bản Java hiện đại hỗ trợ *unconditional type patterns*), đoạn này được chấp nhận và vẫn **không khớp nếu giá trị là `null`**.
- Dù phiên bản có cho phép, khi đã có biến `text` kiểu `String`, thường **gọi trực tiếp** `text` hoặc kiểm tra `text != null` nếu đó mới là điều thực sự cần, thay vì pattern dư thừa.

Đây là một thay đổi về **quy tắc biên dịch theo mức `--release`**, nên khi dự án nhắm Java 17 cần kiểm tra với `--release 17`, không suy diễn từ các JDK mới hơn.

## 7. Interface, generic và giới hạn kiểm tra tại runtime

Java generics dùng **type erasure**, vì vậy kiểu đối số như `String` trong `List<String>` không luôn có mặt ở runtime để kiểm tra qua `instanceof`.

Ví dụ hợp lệ:

```java
Object obj = java.util.List.of("one", "two");

if (obj instanceof java.util.List<?> list) {
    System.out.println(list.size()); // 2
}
```

`List<?>` là kiểu có thể dùng để kiểm tra một danh sách mà **chưa biết** loại phần tử. Accessor `list.get(0)` khi đó có thể được xem như `Object`; không thể mặc nhiên gán vào `String` nếu chưa kiểm tra.

Ví dụ **không biên dịch** từ một biến kiểu `Object`:

```java
// CỐ Ý SAI:
Object obj = java.util.List.of("one", "two");
if (obj instanceof java.util.List<String> words) {
    System.out.println(words.get(0));
}
```

Compiler không thể kiểm tra đối số `String` của `List<String>` từ một `Object` theo cách này; type argument không phải thông tin reifiable của object. Tránh cast `(List<String>)` mù quáng vì có thể tạo cảnh báo unchecked và dẫn đến lỗi khi lấy phần tử. Khi cần chắc chắn toàn bộ phần tử là `String`, kiểm tra từng phần tử/validate dữ liệu theo hợp đồng API.

**Sắc thái quan trọng:** quy tắc cho `instanceof` với parameterized types còn phụ thuộc vào **kiểu tĩnh của biểu thức và tính hợp lệ của casting conversion**. Không kết luận máy móc rằng mọi trường hợp dùng type argument cụ thể sau `instanceof` đều bị cấm. Trường hợp `Object` → `List<String>` ở trên không hợp lệ; `List<?>` là lựa chọn tổng quát phù hợp nhất cho dữ liệu có kiểu phần tử chưa rõ.

### 7.1. Mảng có kiểu thành phần tại runtime

Khác với generic type arguments bị xóa, mảng Java lưu thông tin kiểu thành phần cho kiểm tra runtime:

```java
Object data = new String[] {"a", "b"};

if (data instanceof String[] names) {
    System.out.println(names.length); // 2
}
```

Điều này có thể hữu ích khi xử lý input hỗn hợp từ thư viện cũ. Dù vậy, hãy chọn interface/kiểu nhận đầu vào rõ ràng thay vì lặp các kiểm tra kiểu nếu có thể.

## 8. Khi nào dùng `instanceof`, khi nào dùng đa hình?

| Nhu cầu | Cách ưu tiên | Lý do |
| --- | --- | --- |
| Gọi hành vi chung `name()` của mọi đối tượng `Named` | `value.name()` qua interface | Không cần biết subtype |
| Cần method riêng `breed()` của `Dog` | `if (value instanceof Dog dog)` | Có guard, có biến `Dog` đúng kiểu |
| Nhận `Object` từ biên API và phân loại dữ liệu | Pattern có nhánh fallback rõ ràng | Input động cần kiểm tra ở runtime |
| Nhận nhiều loại xử lý cùng hành vi nhưng có thể thiết kế interface chung | Thiết kế interface/phương thức đa hình | Tránh các nhánh `instanceof` rải rác |
| Chỉ cần chống `ClassCastException` khi chuyển từ kiểu cha sang subtype | Pattern trước khi dùng method subtype | Không cast mù |
| Logic dựa vào các trường của record | Type pattern (Java 17+) hoặc record pattern nếu dự án dùng Java 21+ | Tách rõ feature và yêu cầu phiên bản |
| Chỉ kiểm tra `null` trên biến đã có kiểu cần dùng | `value != null` | Pattern có thể dư thừa |

**Record pattern** (deconstruction) là một cơ chế khác, đã chính thức từ Java 21, có thể kiểm tra kiểu record và trích xuất component ở một mẫu. Bài này tập trung vào **type pattern** như `obj instanceof Badge b`, vốn tương thích Java 17+. Khi nâng cấp sang record patterns, vẫn phải tuân thủ ràng buộc subtype/interface, kiểm tra `null` và phạm vi biến theo đặc tả của phiên bản đích.

### 8.1. Không dựa vào việc phân loại kiểu cho mọi thay đổi nghiệp vụ

Nếu mỗi lần thêm subclass phải sửa hàng chục khối `if (x instanceof SubType)`, thường nên xem lại thiết kế: chuyển hành vi chung vào interface hoặc abstract method của superclass. Pattern hữu ích ở các **ranh giới xử lý** (parser, adapter, event dispatch, đọc dữ liệu từ plugin, logging) hoặc khi subtype có khả năng thực sự khác biệt.

## 9. Chương trình Java 17+ độc lập, đã kiểm tra đầu ra

Lưu thành file chính xác **`PatternHierarchyDemo.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class PatternHierarchyDemo {
    interface Named { String name(); }

    static abstract class Animal implements Named {
        private final String name;

        protected Animal(String name) {
            this.name = Objects.requireNonNull(name);
        }

        @Override
        public String name() { return name; }
    }

    static final class Dog extends Animal {
        private final String breed;

        Dog(String name, String breed) {
            super(name);
            this.breed = Objects.requireNonNull(breed);
        }

        String breed() { return breed; }
    }

    static final class Cat extends Animal {
        Cat(String name) { super(name); }
    }

    record Badge(String name, int level) implements Named {}

    static String describe(Object object) {
        if (object instanceof Dog dog && dog.breed().startsWith("B")) {
            return "dog:" + dog.name() + ":" + dog.breed();
        }
        if (object instanceof Badge badge) {
            return "badge:" + badge.name() + "#" + badge.level();
        }
        if (object instanceof Named named) {
            return "named:" + named.name();
        }
        if (object instanceof List<?> list) {
            return "list-size:" + list.size();
        }
        return "other";
    }

    static String upperOrFallback(Object input) {
        if (!(input instanceof String text)) {
            return "not string";
        }
        return text.toUpperCase(Locale.ROOT);
    }

    static String legacyDogBreed(Object input) {
        if (input instanceof Dog) {
            Dog dog = (Dog) input;
            return dog.breed();
        }
        return "not dog";
    }

    static String interfaceDispatch(Named value) {
        return value.name();
    }

    public static void main(String[] args) {
        Object dog = new Dog("Milo", "Beagle");
        System.out.println(describe(dog));
        System.out.println(describe(new Cat("Nora")));
        System.out.println(describe(new Badge("STAFF", 3)));
        System.out.println(describe(List.of("one", "two")));
        System.out.println(describe(null));
        System.out.println(upperOrFallback("java"));
        System.out.println(upperOrFallback(7));
        System.out.println("legacy=" + legacyDogBreed(dog));
        System.out.println("interface="
                + interfaceDispatch(new Badge("TEAM", 1)));

        try {
            String forced = (String) dog;
            System.out.println(forced);
        } catch (ClassCastException ex) {
            System.out.println("bad cast -> ClassCastException");
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac --release 17 PatternHierarchyDemo.java
java PatternHierarchyDemo
```

Kết quả **chính xác**:

```text
dog:Milo:Beagle
named:Nora
badge:STAFF#3
list-size:2
other
JAVA
not string
legacy=Beagle
interface=TEAM
bad cast -> ClassCastException
```

### Giải thích kết quả

1. **`dog:Milo:Beagle`**: biến có kiểu tĩnh `Object` nhưng đối tượng là `Dog`; pattern `Dog dog` khớp và điều kiện `dog.breed().startsWith("B")` đúng.
2. **`named:Nora`**: `Cat` không khớp `Dog` hay `Badge`, nhưng kế thừa `Animal` triển khai `Named`; vì vậy khớp `Named named`.
3. **`badge:STAFF#3`**: `Badge` là record triển khai interface `Named`, nhưng nhánh `Badge` đứng trước nhánh interface rộng hơn và được chọn.
4. **`list-size:2`**: đối tượng `List` khớp `List<?> list`; có thể dùng `size()` mà không cần biết kiểu phần tử.
5. **`other`**: `null` không khớp bất kỳ type pattern nào.
6. **`JAVA`**: hàm `upperOrFallback` dùng phủ định pattern + return sớm; biến `text` hợp lệ sau guard.
7. **`not string`**: `Integer` không khớp `String`, trả về fallback an toàn.
8. **`legacy=Beagle`**: kiểm tra kiểu rồi cast thủ công vẫn hợp lệ nhưng dài hơn.
9. **`interface=TEAM`**: method `name()` của `Badge` đáp ứng `Named`; gọi qua interface không cần pattern.
10. **`bad cast -> ClassCastException`**: ép kiểu trực tiếp từ biến `Object` tham chiếu `Dog` sang `String` thất bại lúc chạy; exception được bắt có chủ đích.

## 10. Các lỗi biên dịch và lỗi runtime cần phân biệt

### Lỗi A — Cố dùng biến pattern sau `||`

```java
// WrongScope.java — CỐ Ý SAI:
class WrongScope {
    static boolean f(Object obj) {
        return obj instanceof String s || s.isEmpty();
    }
}
```

Với `javac --release 17 WrongScope.java`, compiler không tìm thấy `s` ở vế phải `||`. Biến pattern không bảo đảm được gán nếu vế trái sai.

### Lỗi B — Dùng tham số generic không kiểm tra được

```java
// NonReifiable.java — CỐ Ý SAI:
import java.util.List;

class NonReifiable {
    static boolean f(Object data) {
        return data instanceof List<String> words;
    }
}
```

Với `javac --release 17 NonReifiable.java`, compiler báo `Object cannot be safely cast to List<String>`. Có thể kiểm tra `List<?>`, sau đó kiểm tra nội dung nếu ứng dụng thật sự yêu cầu kiểu phần tử.

### Lỗi C — Test/cast không có quan hệ kiểu phù hợp

```java
// CỐ Ý SAI:
String text = "A";
boolean match = text instanceof Integer; // String và Integer không tương thích
```

Đây là lỗi **compile time**; Java không cho phép biểu thức không thể chuyển kiểu như vậy. Nếu biến có kiểu `Object` thì `obj instanceof Integer` có thể biên dịch và cho `false` khi đối tượng không phải `Integer`.

### Lỗi D — Cast không guard

```java
Object value = new Object();
String text = (String) value; // COMPILE được, ClassCastException khi chạy
```

Đây là lỗi **runtime**, khác với lỗi C. Cách sửa là thiết kế API với kiểu đúng hoặc dùng `if (value instanceof String s)` rồi sử dụng `s`.

### Lỗi E — Mẫu dư thừa và khác biệt Java 17/21

```java
// AlwaysTrue.java — test không cần thiết:
class AlwaysTrue {
    static boolean f(String text) {
        return text instanceof String value;
    }
}
```

Với `--release 17`, compiler từ chối mẫu vô điều kiện; với `--release 21`, ví dụ trên biên dịch được. Không đánh đồng lỗi theo mức ngôn ngữ với quy tắc của mọi JDK hiện đại. Đối với mã hỗ trợ cả Java 17 và Java 21+, thay bằng `return text != null;` nếu mục đích thật sự là kiểm tra khác `null`.

## 11. Bài tập tự đánh giá

**Câu 1:** Với `Animal a = new Dog("Milo", "Beagle");`, vì sao `a.name()` hợp lệ nhưng `a.breed()` không biên dịch?

**Đáp án:** Kiểu tĩnh `Animal` bảo đảm method `name()`, không khai báo `breed()`. Dùng `if (a instanceof Dog dog) { dog.breed(); }` khi cần hành vi riêng.

**Câu 2:** Với `Named n = new Badge("STAFF", 3);`, vì sao `n.name()` hợp lệ nhưng `n.level()` không hợp lệ?

**Đáp án:** `Named` chỉ công bố `name()`. Mẫu `n instanceof Badge badge` cho phép gọi `badge.level()` nếu đối tượng runtime thật là `Badge`.

**Câu 3:** `Object o = null; if (o instanceof Object x) { ... }` có vào nhánh `if` không?

**Đáp án:** Không. Type pattern qua `instanceof` không khớp `null`, kể cả kiểu đích là `Object`.

**Câu 4:** Tại sao `if (o instanceof String s && s.length() > 3)` hợp lệ còn `if (o instanceof String s || s.length() > 3)` sai?

**Đáp án:** Với `&&`, đánh giá vế phải chỉ khi mẫu đã khớp và `s` đã được khởi tạo; với `||`, vế phải có thể chạy khi mẫu sai.

**Câu 5:** `Object o = List.of("A");` có thể kiểm tra `o instanceof List<String> words` không?

**Đáp án:** Không theo cách viết đó vì generic element type không thể được kiểm tra an toàn từ `Object`. Dùng `List<?>` để kiểm tra kiểu danh sách rồi validate phần tử.

**Câu 6:** Để in tên của mọi `Named`, nên dùng `if (n instanceof Dog d) ... else if (n instanceof Badge b) ...` hay `n.name()`?

**Đáp án:** `n.name()` là lựa chọn phù hợp hơn vì hành vi chung đã có trong interface. Pattern chỉ cần khi thật sự xử lý thuộc tính hoặc hành vi riêng của subtype.

**Câu 7:** Hai object thuộc các class khác nhau đều triển khai `Named` có thể cùng khớp `instanceof Named named` không?

**Đáp án:** Có. Interface test dựa trên kiểu triển khai thực tế, không yêu cầu các object có cùng class cụ thể.

## 12. Checklist khi viết mã thực tế

- [ ] Xác định kiểu tĩnh của biểu thức (`Object`, superclass, interface) và kiểu runtime có thể xuất hiện.
- [ ] Dùng `obj instanceof SubType value` khi cần API riêng của subtype, dùng biến `value` thay cho cast lần hai.
- [ ] Ưu tiên method chung trên superclass/interface khi nhiệm vụ không phụ thuộc vào subtype.
- [ ] Thứ tự nhánh cụ thể → rộng trong chuỗi `if/else if` khi một đối tượng có thể khớp nhiều kiểu.
- [ ] Nhớ `null` luôn làm type pattern `instanceof` không khớp.
- [ ] Tôn trọng flow scoping: `&&` và guard-return có thể giúp biến pattern còn hợp lệ; `||`/`else` không mặc nhiên làm được điều đó.
- [ ] Không cast mù từ `Object`; phân biệt lỗi compiler vì không có quan hệ kiểu với `ClassCastException` lúc chạy.
- [ ] Với generics, dùng `List<?>` khi kiểm tra một object không rõ phần tử; không suy ra `List<String>` từ runtime.
- [ ] Kiểm tra mức `--release` thực tế, nhất là quy tắc của unconditional patterns có khác biệt giữa Java 17 và Java 21.
- [ ] Tránh preview syntax nếu dự án chỉ dùng các tính năng chính thức; dùng type pattern ổn định Java 16+.

## Tài liệu chuẩn còn áp dụng

- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html): ví dụ quan hệ subclass, phép ép kiểu và phạm vi biến pattern.
- [Java Language Specification, Java SE 25 — `15.20.2 The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.20.2): kiểm tra kiểu, tương thích ép kiểu, quy tắc runtime của `instanceof`.
- [Java Language Specification, Java SE 25 — `6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.3): flow scoping của pattern variables với `&&`, `||`, `!` và `if`.
- [Oracle Java 16 — Java Language Changes](https://docs.oracle.com/en/java/javase/16/language/java-language-changes.html): mốc tính năng `instanceof` pattern matching trở thành chính thức.
