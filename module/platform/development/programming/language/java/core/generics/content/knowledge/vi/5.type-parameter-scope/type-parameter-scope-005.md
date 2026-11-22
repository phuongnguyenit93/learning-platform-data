# Lớp thành viên bên trong và tham số kiểu của lớp bao trong Java

Một **lớp thành viên bên trong** (*non-static member inner class*) được khai báo trong thân một lớp khác mà **không có từ khóa `static`**. Nếu lớp bao khai báo tham số kiểu `T`, inner class có thể sử dụng `T` trong field, constructor và phương thức của mình mà **không cần khai báo lại**. Một inner class cũng có thể khai báo tham số kiểu riêng, chẳng hạn `U`.

Ví dụ điển hình là `Outer<T>.Inner<U>`: `T` gắn với kiểu tham số hóa của lớp bao, còn `U` là tham số kiểu của chính lớp bên trong. Mỗi đối tượng inner luôn được gắn với **một đối tượng outer cụ thể**, nên cách tạo đối tượng và cách truy cập thành viên khác với `static nested class`.

Bài này giải thích phạm vi biến kiểu, cú pháp tạo đối tượng, cách đọc `Outer<String>.Inner<Integer>`, quan hệ giữa hai lớp, giới hạn của generics, sự khác biệt với `static nested class`, và các trường hợp sử dụng phù hợp. Các ví dụ Java dùng cú pháp chạy được với JDK 17 trở lên.

## 1. Cú pháp cơ bản: inner class dùng `T` của outer class

Xét lớp `Container<T>`:

```java
class Container<T> {
    private final T stored;

    Container(T stored) {
        this.stored = stored;
    }

    class View {
        T get() {
            return stored;
        }
    }
}
```

Những điểm cần đọc chính xác:

- `Container<T>` khai báo type parameter `T`.
- `View` là **non-static member inner class** vì nằm trong `Container` và không có `static`.
- `View` **không khai báo `<T>` riêng**; khi viết `T get()`, nó đang dùng `T` thuộc phạm vi của `Container<T>`.
- `View` có thể truy cập field `stored`, kể cả field `private`, bởi Java cho các thành viên thuộc cùng cấu trúc lồng truy cập nhau theo quy tắc ngôn ngữ.
- Đối tượng `View` phải được gắn với một đối tượng `Container` đã được tạo.

Trong ngữ cảnh có thể chạy:

```java
Container<String> container = new Container<>("Java");
Container<String>.View view = container.new View();

String text = view.get(); // Kiểu trả về là String.
```

Ở đây, `Container<String>.View` được hiểu là **kiểu `View` thuộc outer có kiểu `Container<String>`**. Vì `T = String`, `View.get()` được kiểm tra như phương thức trả `String`.

Không có `View<T>` ở đây: lớp `View` chưa tự khai báo tham số kiểu. Viết `Container<String>.View<String>` sẽ sai vì `View` không nhận đối số kiểu riêng.

## 2. Tại sao inner class nhìn thấy tham số kiểu của lớp bao?

Phạm vi của một type parameter khai báo trên class bao trùm các thành viên instance thích hợp của class đó, bao gồm khai báo member inner class không `static`. Vì inner class nằm trong ngữ cảnh instance của outer, Java có thể diễn đạt các thành viên của nó bằng chính tham số kiểu của outer.

```java
class ResultBox<T> {
    private final T result;

    ResultBox(T result) {
        this.result = result;
    }

    class Reader {
        T read() {
            return result;
        }

        void print() {
            System.out.println(result);
        }
    }
}
```

`Reader.read()` **không phải generic method tự khai báo `<T>`**. Nó chỉ dùng `T` từ `ResultBox<T>`. Khi đối tượng outer được sử dụng qua `ResultBox<Long>`, kết quả `read()` có kiểu `Long`; với `ResultBox<String>`, kết quả có kiểu `String`.

**Không cần lặp lại `<T>` trên `Reader`.** Việc tự khai báo `class Reader<T>` trong `ResultBox<T>` tạo một **tham số kiểu mới có cùng tên**, có khả năng che khuất `T` của outer trong phạm vi inner. Đó không phải cách “kế thừa” `T` và rất dễ gây nhầm lẫn. Nếu inner cần kiểu riêng, nên đặt tên như `<U>` để phân biệt.

Phạm vi cú pháp `T` và việc gắn inner với outer là hai khía cạnh liên quan nhưng khác nhau: `T` phục vụ **kiểm tra kiểu tĩnh**, còn một inner object có liên hệ với **đối tượng outer cụ thể** ở thời gian chạy.

## 3. Inner class có tham số kiểu riêng: `Outer<T>.Inner<U>`

Khi mỗi inner object cần thêm một kiểu độc lập, khai báo type parameter mới tại inner class:

```java
class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    class Inner<U> {
        private final U extra;

        Inner(U extra) {
            this.extra = extra;
        }

        T outerValue() {
            return value;
        }

        U innerValue() {
            return extra;
        }
    }
}
```

Trong ví dụ:

- `T` được khai báo bởi `Outer<T>`.
- `U` được khai báo bởi `Inner<U>`.
- `outerValue()` trả `T` của outer.
- `innerValue()` trả `U` của inner.
- Không có ràng buộc bắt buộc rằng `T` và `U` phải là cùng một kiểu.

Cách dùng:

```java
Outer<String> outer = new Outer<>("Java");
Outer<String>.Inner<Integer> inner = outer.new Inner<>(17);

String language = inner.outerValue();
Integer version = inner.innerValue();
```

`Outer<String>.Inner<Integer>` là một kiểu có **hai thông tin generic ở hai cấp**. `String` được truyền vào `Outer<T>`, còn `Integer` được truyền vào `Inner<U>`.

Đọc từ ngoài vào trong:

| Thành phần | Ý nghĩa |
| --- | --- |
| `Outer<T>` | Lớp bao khai báo `T` |
| `Outer<String>` | Outer đã được tham số hóa với `T = String` |
| `Inner<U>` | Inner khai báo `U` riêng |
| `Outer<String>.Inner<Integer>` | Inner có `T = String` từ outer và `U = Integer` của riêng inner |
| `outer.new Inner<>(17)` | Tạo inner gắn với `outer`; `U` được suy luận từ ngữ cảnh/đối số |
| `inner.outerValue()` | Trả `String` |
| `inner.innerValue()` | Trả `Integer` |

Một outer có thể tạo **nhiều inner object với các kiểu `U` khác nhau**:

```java
Outer<String>.Inner<Integer> count = outer.new Inner<>(3);
Outer<String>.Inner<Boolean> enabled = outer.new Inner<>(true);
```

Các inner object này cùng liên hệ với outer mang `T = String`, nhưng mỗi inner có kiểu riêng cho `U`.

### Khác nhau giữa type parameter và object instance

Hai biểu thức `outer.new Inner<>(3)` và `anotherOuter.new Inner<>(3)` có thể cùng kiểu tĩnh `Outer<String>.Inner<Integer>` nếu hai outer đều là `Outer<String>`. Tuy vậy, inner tạo ra vẫn gắn với **hai outer object khác nhau** và có thể thấy hai trạng thái outer khác nhau. Type argument không mô tả **danh tính đối tượng**.

## 4. Cách tạo inner object: `outer.new Inner(...)`

Khởi tạo non-static inner class từ mã nằm ngoài outer cần một **enclosing instance** hợp lệ:

```java
Outer<String> outer = new Outer<>("Java");
Outer<String>.Inner<Integer> inner = outer.new Inner<>(17);
```

Cú pháp `outer.new Inner<>(17)` nhấn mạnh rằng inner object được tạo **trong quan hệ với chính outer object `outer`**.

Những dạng dưới đây được đưa ra để nhận diện lỗi, **không phải mã hợp lệ để chạy**:

```java
// Sai khi đứng trong ngữ cảnh không có enclosing instance thích hợp:
// Outer<String>.Inner<Integer> x = new Inner<>(17);

// Sai: inner không phải lớp static độc lập có thể tạo trực tiếp như thế.
// Outer<String>.Inner<Integer> x = new Outer.Inner<>(17);
```

Nếu tạo inner từ một **instance method của outer**, Java đã có enclosing instance hiện tại và có thể viết `new Inner<>(...)`:

```java
class Outer<T> {
    class Inner<U> {
        Inner(U data) {}
    }

    <U> Inner<U> create(U value) {
        return new Inner<>(value);
    }
}
```

Đây là đoạn minh họa độc lập với khai báo `Outer<T>` trước đó. `create` tự khai báo `<U>` vì phương thức cần biểu diễn kiểu giá trị truyền vào; inner class cũng khai báo `U`, nhưng tham số `U` của phương thức và tham số `U` của inner là **hai khai báo riêng** được liên kết thông qua `new Inner<>(value)` và kiểu trả về `Inner<U>`.

Nếu không cần khai báo `<U>` riêng trên `create`, bạn cũng có thể viết một method chỉ trả về một inner với `U` cố định, chẳng hạn `Inner<String> createLabel()`.

### Phân biệt với constructor của outer

Lệnh `new Outer<String>("Java")` tạo **outer object**. Sau đó `outer.new Inner<>(17)` tạo **inner object** liên hệ với outer đó. Java không tự tạo outer mới khi bạn gọi constructor của non-static inner class.

Một inner object có thể được truyền ra ngoài phạm vi tạo ban đầu, nhưng vẫn mang quan hệ với enclosing instance đã chọn. Đặc điểm này quan trọng trong việc thiết kế vòng đời đối tượng.

## 5. Ví dụ hoàn chỉnh Java 17+: cùng inner class, hai kiểu outer và inner khác nhau

Lưu toàn bộ nội dung sau vào **`Main.java`**. Chương trình có:

1. `Folder<T>` là lớp bao generic, giữ một nhãn kiểu `T`.
2. `Item<U>` là **non-static inner class** dùng cả `T` của outer và `U` của chính nó.
3. `Tag<V>` là **static nested class** có `V` riêng; nó không nhận `T` từ outer.
4. Hai đối tượng outer tạo inner có các cặp kiểu khác nhau.

```java
public class Main {
    static final class Folder<T> {
        private final T label;

        Folder(T label) {
            this.label = label;
        }

        final class Item<U> {
            private final U value;

            Item(U value) {
                this.value = value;
            }

            T ownerLabel() {
                return Folder.this.label;
            }

            U payload() {
                return value;
            }

            String describe() {
                return "label=" + label + ", value=" + value;
            }
        }

        static final class Tag<V> {
            private final V value;

            Tag(V value) {
                this.value = value;
            }

            V value() {
                return value;
            }
        }
    }

    public static void main(String[] args) {
        Folder<String> language = new Folder<>("Java");
        Folder<String>.Item<Integer> page = language.new Item<>(17);
        System.out.println("page: " + page.describe());

        Folder<Integer> priority = new Folder<>(3);
        Folder<Integer>.Item<String> note =
                priority.new Item<>("urgent");
        System.out.println("note: " + note.describe());

        Folder.Tag<String> tag = new Folder.Tag<>("shared");
        System.out.println("tag: " + tag.value());

        System.out.println("owner: " + page.ownerLabel());
        System.out.println("payload: " + page.payload());

        // Folder<String>.Item<String> wrong = language.new Item<>(17);
        // Không biên dịch: inner cần U = String, nhưng nhận Integer.
    }
}
```

Biên dịch/chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Stdout:**

```text
page: label=Java, value=17
note: label=3, value=urgent
tag: shared
owner: Java
payload: 17
```

Diễn giải:

- `language` là `Folder<String>`; vì thế `page.ownerLabel()` có kiểu `String`.
- `page` là `Folder<String>.Item<Integer>`; vì thế `page.payload()` có kiểu `Integer`. Method `describe()` có thể đọc field `label` của outer và `value` của inner.
- `priority` là `Folder<Integer>`; vì thế `note.ownerLabel()` trả `Integer` và `note.payload()` trả `String`.
- `Folder.Tag<String>` là static nested class: `V = String` do chính `Tag<V>` khai báo, không lấy type parameter `T` của `Folder<T>`.
- Dòng sai kiểu được để comment để chương trình biên dịch bình thường; nếu bật lại, trình biên dịch từ chối do đối số constructor không khớp `U = String`.

`Folder` được khai báo `static` bên trong `Main` chỉ để dễ đóng gói chương trình độc lập. Điều đó **không làm `Item` trở thành static**: `Item` vẫn là non-static inner class của `Folder`, còn `Tag` là static nested class của `Folder`.

## 6. `Outer.this` và cách truy cập đối tượng bao

Vì một inner object có enclosing instance, code của inner có thể đọc các instance members hợp lệ của outer, kể cả thành viên `private`:

```java
class Counter<T> {
    private final T name;
    private int count;

    Counter(T name) {
        this.name = name;
    }

    class Incrementer {
        void increase() {
            count++;
        }

        T label() {
            return Counter.this.name;
        }
    }
}
```

Ở đây:

- `count++` truy cập field của enclosing `Counter` khi không có thành viên inner cùng tên gây che khuất.
- `Counter.this.name` nêu rõ **instance `Counter` bao quanh** của inner hiện tại.
- `label()` trả `T` thuộc outer; bản thân `Incrementer` không khai báo tham số kiểu mới.

`Outer.this` hữu ích khi inner và outer có các field trùng tên:

```java
class Example<T> {
    T value;

    class Inner {
        String value;

        T outerValue() {
            return Example.this.value;
        }

        String innerValue() {
            return this.value;
        }
    }
}
```

`this.value` trỏ field của inner; `Example.this.value` trỏ field của outer. Lưu ý đây là **che khuất tên field**, khác với việc che khuất **tên type parameter**. Cả hai đều liên quan đến scope nhưng do các khai báo khác nhau tạo ra.

Một inner instance có thể truy cập trạng thái outer, nhưng điều đó **không bảo đảm trạng thái bất biến**. Nếu outer có các field mutable, inner có thể quan sát hoặc gây ra thay đổi của outer theo phương thức được khai báo.

## 7. Inner class dùng `T` của outer mà không khai báo type parameter riêng

Không phải inner nào cũng cần `<U>`. Ví dụ thiết kế một con trỏ đọc dữ liệu của kho:

```java
class Vault<T> {
    private final T secret;

    Vault(T secret) {
        this.secret = secret;
    }

    class Reader {
        T read() {
            return secret;
        }
    }
}
```

Sử dụng:

```java
Vault<String> vault = new Vault<>("key");
Vault<String>.Reader reader = vault.new Reader();
String result = reader.read();
```

`Reader` không phải generic class **do bản thân nó khai báo type parameter**. Nhưng **kiểu `Vault<String>.Reader` vẫn phụ thuộc vào cách tham số hóa của outer**. Vì vậy, không nên nhầm “inner không có `<U>`” với “inner không bị ảnh hưởng bởi generics”.

Nếu mục tiêu chỉ là giữ một đối tượng tham chiếu đến outer và cung cấp các phương thức dùng `T`, kiểu thiết kế này thường đủ. Chỉ thêm `<U>` khi inner thật sự cần một kiểu độc lập mới.

## 8. Non-static inner class và static nested class

Hai hình thức cùng được khai báo **trong thân một lớp**, nhưng mối quan hệ với enclosing instance hoàn toàn khác nhau.

### 8.1. Non-static member inner class

```java
class Owner<T> {
    private final T name;

    Owner(T name) {
        this.name = name;
    }

    class Inner {
        T ownerName() {
            return name;
        }
    }
}
```

Một `Owner<String>.Inner` được gắn với object `Owner<String>`, nên có thể dùng `T` của lớp bao và truy cập field `name` của outer.

### 8.2. Static nested class

```java
class Owner<T> {
    static class Metadata<U> {
        private final U data;

        Metadata(U data) {
            this.data = data;
        }

        U data() {
            return data;
        }
    }
}
```

`Metadata<U>` không có enclosing instance `Owner<T>`, nên **không thể trực tiếp sử dụng tham số kiểu `T` thuộc lớp bao** hay đọc field instance của outer nếu không có một tham chiếu đối tượng được truyền vào.

Cách dùng:

```java
Owner.Metadata<String> meta = new Owner.Metadata<>("info");
String info = meta.data();
```

Cú pháp đúng là `Owner.Metadata<String>`. Không viết `Owner<Integer>.Metadata<String>`: static nested type không mang type argument của lớp bao trong phần định danh kiểu. Nếu nó cần thao tác với `T`, hãy khai báo tham số kiểu của chính `Metadata` hoặc truyền một object outer có kiểu cụ thể thích hợp.

### So sánh trực tiếp

| Tiêu chí | Non-static inner | Static nested |
| --- | --- | --- |
| Khai báo | `class Inner` bên trong outer | `static class Nested` bên trong outer |
| Có enclosing instance của outer | Có | Không |
| Trực tiếp dùng `T` của `Outer<T>` | Có, khi không bị che khuất | Không |
| Có thể khai báo kiểu riêng `<U>` | Có | Có |
| Kiểu tham chiếu thường gặp | `Outer<String>.Inner<Integer>` | `Outer.Nested<Integer>` |
| Tạo từ ngoài outer | `outer.new Inner<>(...)` | `new Outer.Nested<>(...)` |
| Truy cập `Outer.this` | Có khi có enclosing instance phù hợp | Không |
| Hợp lý khi | Hành vi phụ thuộc một outer object cụ thể | Thành phần chỉ được nhóm theo tên và độc lập outer object |

**Quy tắc thiết kế:** nếu nested class không cần đọc hoặc sửa trạng thái của một outer object, cân nhắc `static nested class` để tránh giữ một tham chiếu enclosing không cần thiết. Nếu nested class làm việc mật thiết với trạng thái riêng của outer, non-static inner class là lựa chọn có chủ đích.

## 9. Ràng buộc kiểu ở outer và inner

Outer có thể giới hạn `T`, inner có thể đặt bound cho `U` mà không làm thay đổi trách nhiệm của nhau:

```java
class NumberOwner<T extends Number> {
    private final T number;

    NumberOwner(T number) {
        this.number = number;
    }

    class Caption<U extends CharSequence> {
        private final U text;

        Caption(U text) {
            this.text = text;
        }

        double numericValue() {
            return number.doubleValue();
        }

        int textLength() {
            return text.length();
        }
    }
}
```

Ở đây `T extends Number` bảo đảm outer hỗ trợ `doubleValue()`, còn `U extends CharSequence` bảo đảm inner hỗ trợ `length()`. Khai báo đúng:

```java
NumberOwner<Integer> outer = new NumberOwner<>(7);
NumberOwner<Integer>.Caption<String> caption =
        outer.new Caption<>("level");
```

`NumberOwner<String>` là lỗi vì `String` không kế thừa `Number`. `Caption<Integer>` là lỗi vì `Integer` không triển khai `CharSequence`.

Bound kiểm tra **kiểu tham chiếu**, không tự kiểm tra giá trị cụ thể. `NumberOwner<Double>` vẫn có thể chứa `Double.NaN`; `Caption<String>` vẫn có thể chứa chuỗi rỗng nếu constructor không kiểm tra.

## 10. Các trường hợp phạm vi dễ nhầm

### 10.1. Không khai báo lại `<T>` chỉ để dùng `T` của outer

```java
class Outer<T> {
    class Good {
        T getValue() {
            return null;
        }
    }
}
```

`Good` dùng `T` outer. Nếu viết `class Good<T>` thì tên `T` của inner **che khuất** `T` outer trong phạm vi của inner; loại `T` mới không tự đồng nhất với `T` cũ. Để tránh nhầm, đặt tên `U` khi inner cần type parameter riêng.

Đoạn `return null` ở đây chỉ minh họa cú pháp type scope, không phải logic triển khai đầy đủ.

### 10.2. Một phương thức trong inner có thể có type parameter riêng

```java
class Outer<T> {
    class Inner {
        <U> U echo(U value) {
            return value;
        }
    }
}
```

`U` trong `<U> U echo(U value)` thuộc **method**, không thuộc `Outer` hay `Inner`. Vì vậy một outer `Outer<String>` có thể có inner gọi `echo(5)` và `echo(true)` với kiểu `U` khác nhau. Việc phương thức dùng chung tên với một type parameter ở phạm vi ngoài, nếu có, cần được xem xét để tránh che khuất.

### 10.3. Non-static member inner class khác local class và anonymous class

Một **member inner class** như `Outer<T>.Inner` có tên và được khai báo trực tiếp trong thân outer. Một **local class** được khai báo trong block/method; một **anonymous class** không có tên khai báo riêng. Các dạng class lồng này có quy tắc ngữ cảnh và phạm vi riêng, nhất là khi được khai báo trong static context.

Không nên dùng cú pháp `Outer<T>.Inner<U>` một cách máy móc cho local hoặc anonymous class: nó dành cho member inner type có tên. Bài này tập trung vào **lớp thành viên bên trong** theo đúng phạm vi bài học.

### 10.4. Khai báo inner trong static context và vai trò của `this`

Một method `static` không có enclosing instance outer hiện tại. Nó có thể tạo inner nếu được cung cấp **một outer object rõ ràng**:

```java
class Outer<T> {
    class Inner {
        T get() {
            return null;
        }
    }

    static <T> Outer<T>.Inner make(Outer<T> outer) {
        return outer.new Inner();
    }
}
```

Ở đây `<T>` của `make` là **type parameter riêng của static method**; nó không phải `T` của `class Outer<T>`. Vì nhận `Outer<T> outer` qua đối số, static method có đủ outer instance để tạo inner.

Trong khi đó, khai báo static method chỉ viết `static Outer<T>.Inner make()` mà không tự khai báo `T` là sai vì static member không thể trực tiếp dùng type parameter của outer instance.

## 11. Type erasure và quan hệ đối tượng lúc chạy

Generics trong Java chủ yếu được triển khai bằng **type erasure**: compiler kiểm tra type arguments lúc biên dịch rồi xóa phần lớn thông tin kiểu ấy khỏi bytecode runtime. Thực thể `Outer<String>.Inner<Integer>` không trở thành một lớp JVM riêng so với `Outer<Long>.Inner<Boolean>`.

Tuy vậy, non-static inner instance vẫn gắn với một enclosing outer object. Đây là **quan hệ object thật lúc chạy**, không chỉ là ký hiệu generic:

- Cú pháp `outer.new Inner(...)` chọn outer object cụ thể.
- Bên trong, `Outer.this` tham chiếu enclosing instance ấy.
- Biên dịch thường tạo cơ chế lưu tham chiếu enclosing cho non-static inner object.
- Nếu giữ inner sống lâu, outer có thể tiếp tục được giữ trong bộ nhớ qua quan hệ tham chiếu, tùy đồ thị tham chiếu thực tế.

Không nên suy luận rằng vì type erasure xóa `T` nên inner “mất quyền” truy cập outer object. **Generic type metadata** và **liên kết đối tượng** là hai cơ chế khác nhau.

Tương tự, không thể dùng `instanceof Outer<String>.Inner<Integer>` để xác minh chính xác hai type arguments; kiểu tham số hóa cụ thể không phải một runtime type có thể kiểm tra trực tiếp theo cách đó. Với dữ liệu đến từ reflection, JSON hoặc raw types, cần kiểm tra ranh giới dữ liệu bằng cơ chế thích hợp.

## 12. Khi nào inner class phù hợp?

**Phù hợp:** inner object là một **thành phần gắn với một outer instance cụ thể**, cần gọi phương thức hoặc đọc field của outer và sử dụng cùng type parameter `T`. Ví dụ con trỏ, view, iterator hoặc builder có quan hệ chặt với trạng thái của đối tượng bao.

**Cân nhắc static nested class:** nested type được nhóm theo outer về mặt tổ chức mã nhưng không cần `Outer.this` hoặc trạng thái object. Một helper chứa cấu hình riêng, mô tả metadata hay một value object độc lập thường dễ quản lý khi không có enclosing reference.

**Cân nhắc top-level class:** nếu nested type trở thành API công khai dùng rộng rãi, có vòng đời độc lập hoặc cần nhiều lớp khác phụ thuộc, một top-level class có tên riêng có thể rõ hơn. Sự lựa chọn nên dựa trên mối quan hệ nghiệp vụ và cách sử dụng, không dựa vào việc nested class có thể truy cập private members.

**Cân nhắc chi phí vòng đời:** giữ inner instance ở cache hoặc callback lâu dài có thể giữ theo enclosing object. Nếu không cần liên kết này, static nested class thường giúp giảm sự phụ thuộc và tránh giữ reference ngoài ý muốn.

## 13. Lỗi thường gặp và cách sửa

**Lỗi 1 — tạo non-static inner mà không cung cấp outer object:** dùng `outer.new Inner(...)` khi ở bên ngoài instance context; không dùng `new Outer.Inner(...)` như static nested.

**Lỗi 2 — dùng sai tên kiểu trong khai báo:** inner không có type parameter riêng thì `Outer<String>.Inner` là đúng, không viết `Outer<String>.Inner<String>`. Nếu inner khai báo `<U>`, viết `Outer<String>.Inner<Integer>`.

**Lỗi 3 — trộn kiểu outer:** một `Outer<String>.Inner<Integer>` không phải tự động là `Outer<Integer>.Inner<Integer>`. Type argument của outer tham gia vào kiểu thành viên. Đối số kiểu khác nhau không chuyển đổi được chỉ vì cùng class declaration.

**Lỗi 4 — nghĩ inner phải khai báo lại `<T>` để dùng `T` của outer:** điều đó tạo type parameter khác và có thể che khuất tên cũ. Chỉ khai báo `<U>` mới khi cần vai trò kiểu riêng.

**Lỗi 5 — dùng `T` của outer trong static nested class:** static nested không có enclosing instance và không trực tiếp mang type parameter của outer. Khai báo type parameter riêng hoặc truyền `Outer<T>` từ nơi gọi.

**Lỗi 6 — truy cập field trùng tên mà không chỉ rõ scope:** `this.value` là field của inner nếu được khai báo; `Outer.this.value` chỉ field của enclosing outer. Dùng tên đầy đủ khi quan hệ cần rõ ràng.

**Lỗi 7 — xem inner chỉ là cách nhóm file:** non-static inner có liên kết object thật. Nếu không cần liên kết và state, ưu tiên static nested hoặc top-level class.

**Lỗi 8 — hiểu type erasure là không còn outer instance:** erasure làm mất phần lớn type arguments runtime, nhưng không xóa quan hệ enclosing instance của non-static inner.

**Lỗi 9 — quên kiểm tra null/giá trị:** `Outer<String>` không buộc `T` khác `null`, `Inner<Integer>` không buộc số dương. Validation và loại tham chiếu generic là các mối quan tâm độc lập.

## 14. Tự kiểm tra

**Câu 1.** Trong `class Outer<T> { class Inner { T read() {...} } }`, `Inner` có cần khai báo `<T>` nữa không?

**Đáp án:** Không. `Inner` là non-static member inner class và dùng được `T` của outer. Tự khai báo `<T>` lần nữa sẽ tạo type parameter khác, che khuất tên cũ.

**Câu 2.** Với `Outer<String> outer`, tạo một inner có type parameter `Integer` như thế nào?

**Đáp án:** Nếu khai báo `class Inner<U>`, sử dụng `Outer<String>.Inner<Integer> x = outer.new Inner<>(17);`.

**Câu 3.** Vì sao `Outer<String>.Inner<Integer>` biểu diễn hai type arguments chứ không chỉ `Integer`?

**Đáp án:** `T = String` đến từ `Outer<T>`, `U = Integer` đến từ `Inner<U>`. Các method dùng `T` có kiểu `String`, còn method dùng `U` có kiểu `Integer`.

**Câu 4.** `static class Metadata<U>` bên trong `Outer<T>` có thể trực tiếp trả field `T` của outer không?

**Đáp án:** Không, vì static nested class không có enclosing outer instance và không trực tiếp sử dụng `T` của outer. Muốn làm việc với dữ liệu outer cần có tham số kiểu/đối tượng truyền vào phù hợp.

**Câu 5.** Hai inner objects cùng kiểu `Outer<String>.Inner<Integer>` nhưng được tạo từ hai outer objects khác nhau có bắt buộc nhìn thấy cùng state không?

**Đáp án:** Không. Kiểu tĩnh có thể giống nhau, nhưng mỗi inner gắn với một enclosing object cụ thể và do đó có thể nhìn thấy state khác nhau.

**Câu 6.** Vì sao việc giữ một inner object dài hạn có thể làm outer object tiếp tục tồn tại trong bộ nhớ?

**Đáp án:** Non-static inner object có liên hệ tham chiếu đến enclosing outer object; chừng nào graph tham chiếu còn giữ inner và không có cơ chế cắt liên kết thích hợp, outer có thể vẫn reachable qua inner.

## Kết luận

Non-static member inner class nằm trong phạm vi generic của outer, nên có thể sử dụng `T` từ `Outer<T>` mà không cần khai báo lại. Khi cần dữ liệu độc lập, inner có thể khai báo `U` và được sử dụng với kiểu như `Outer<String>.Inner<Integer>`. Khi tạo inner từ bên ngoài, phải có một enclosing object trong biểu thức `outer.new Inner(...)`. Phân biệt nó với `static nested class`: loại static có type parameter của riêng mình, không mang `T` hoặc reference instance của outer theo cách non-static inner class làm. Hiểu cả **phạm vi kiểu lúc biên dịch** và **quan hệ đối tượng khi chạy** giúp chọn cấu trúc lồng phù hợp, giảm lỗi cú pháp và kiểm soát rõ vòng đời của đối tượng.