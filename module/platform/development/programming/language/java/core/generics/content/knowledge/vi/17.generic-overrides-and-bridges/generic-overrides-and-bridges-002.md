# Chữ ký sau xóa kiểu và khái niệm subsignature trong Java Generics

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **chữ ký phương thức trong ngôn ngữ Java**, **chữ ký sau xóa kiểu** (*erased signature*) và **method descriptor** ở bytecode.
2. Áp dụng định nghĩa **subsignature** để xác định chiều ghi đè hợp lệ giữa một phương thức generic/parameterized và phiên bản có chữ ký đã xóa kiểu.
3. Giải thích vì sao hai phương thức có cùng erasure đôi khi ghi đè hợp lệ, đôi khi gây lỗi `name clash`.
4. Hiểu mối liên hệ giữa ghi đè ở mã nguồn, *type erasure*, *bridge method* và dispatch động ở JVM.
5. Chẩn đoán lỗi bằng `javac`, `@Override` và `javap`, rồi chọn cách sửa tránh raw type trong thiết kế API mới.

Bối cảnh: Java generics chủ yếu được hiện thực bằng **type erasure**. Trong khi đó, ghi đè vẫn phải đúng về mặt hệ thống kiểu của mã nguồn. Hai cơ chế gặp nhau ở quy tắc **subsignature**, vốn hỗ trợ sự tương thích khi thư viện tiến hóa từ API cũ sang API có generics.

## 1. “Chữ ký phương thức” nghĩa là gì?

Theo quy tắc chữ ký phương thức Java (JLS `8.4.2), chữ ký xét tới **tên**, **các tham số kiểu của chính phương thức khi có**, và **kiểu của danh sách tham số hình thức** sau khi áp dụng các quy tắc tương ứng về tương đương kiểu và đổi tên tham số kiểu.

Ví dụ:

```java
// Các ví dụ minh họa chữ ký, không đặt cùng phạm vi vì chúng đụng chữ ký:
void find(java.util.List<String> values);
void find(java.util.List<Integer> values);

<T> void transfer(T value);
<U> void transfer(U value);
```

Hai khai báo `find` không có cùng chữ ký nguồn vì tham số hóa `List<String>` và `List<Integer>` khác nhau. Tuy nhiên, chúng sẽ **trùng erasure**, nên không thể khai báo chúng như hai overload trong cùng một lớp. Hai khai báo `transfer` thực chất có **cùng chữ ký** sau khi đổi tên tham số kiểu (`T` ↔ `U`), nên cũng không thể đặt cạnh nhau trong một lớp.

Các yếu tố **không thuộc chữ ký phương thức Java** gồm:

- **Kiểu trả về**: không thể overload chỉ bằng cách đổi `String output()` thành `Object output()`.
- Tên biến tham số: `void log(String name)` và `void log(String text)` cùng chữ ký.
- `throws`: `void read() throws IOException` và `void read()` không tạo hai overload.
- Các modifier như `public`, `private`, `static`, `final`: chúng tác động tính hợp lệ của kế thừa/ghi đè, không làm hai phương thức khác chữ ký.
- Annotation và phần thân phương thức.

Dạng varargs `String...` và dạng mảng `String[]` cho cùng loại tham số mảng trong việc xác định chữ ký; không thể dùng chúng làm hai overload độc lập. Nhưng vì varargs còn quy định cách truyền đối số tại vị trí gọi, hai khai báo có thể khác trải nghiệm khi sử dụng dù chữ ký tương đương.

Đừng nhầm **chữ ký nguồn** với **descriptor của JVM**: descriptor mã hóa kiểu tham số **và kiểu trả về** ở bytecode. Chúng phục vụ hai cấp độ khác nhau; phần 6 sẽ giải thích.

## 2. Type erasure biến chữ ký như thế nào?

Ở bước biên dịch, type erasure loại bỏ hoặc quy về dạng thích hợp các phần tham số hóa trong kiểu. Một số phép biến đổi quan trọng:

| Kiểu được viết trong Java | Kiểu sau erasure | Ý nghĩa |
| --- | --- | --- |
| `List<String>` | `List` | Đối số generic bị loại khỏi kiểu tham chiếu. |
| `Map<String, Integer>` | `Map` | Không còn hai đối số generic trong mô tả kiểu đã xóa. |
| `T`, với `T` không có bound tường minh | `Object` | Giới hạn ngầm là `Object`. |
| `T extends Number` | `Number` | Lấy erasure của giới hạn bên trái. |
| `T extends Number & Comparable<T>` | `Number` | Erasure của type variable dựa trên giới hạn đầu tiên. |
| `List<String>[]` | `List[]` | Erasure áp dụng tới thành phần mảng. |
| `int`, `String`, `String[]` | Không đổi | Các kiểu không cần loại tham số generic vẫn giữ kiểu tương ứng. |

Ví dụ minh họa:

```java
// Trước xóa kiểu:
<T> T identity(T value);
<T extends Number> T twice(T value);
void display(java.util.List<String> values);

// Hình dung dạng mô tả sau xóa kiểu:
// Object identity(Object value);
// Number twice(Number value);
// void display(java.util.List values);
```

Đây là **sơ đồ khái niệm**: đừng sao chép cả hai nhóm vào một lớp như những phương thức riêng. Java compiler có thể giữ thông tin generic trong metadata `Signature` để hỗ trợ reflection/tooling, nhưng descriptor và lời gọi JVM sử dụng kiểu đã xóa khi thích hợp.

**Chữ ký sau xóa kiểu của một phương thức** là chữ ký có cùng tên, với kiểu của từng tham số hình thức được thay bằng erasure tương ứng. Để xác định nó, bạn nên nhìn vào **tham số** và kiểu generic; kiểu trả về được xóa kiểu trong quá trình dịch mã nhưng **không tham gia định nghĩa chữ ký phương thức nguồn**.

Ví dụ:

- `void submit(List<String> values)` → erasure của chữ ký: `submit(List)`.
- `void submit(List<Integer> values)` → erasure của chữ ký: `submit(List)`.
- `<T> void inspect(T value)` → erasure của chữ ký: `inspect(Object)`.
- `<T extends Number> void inspect(T value)` → erasure của chữ ký: `inspect(Number)`.

Vì vậy, hai phương thức khác biệt ở kiểu đối số generic có thể trở thành cùng một điểm gọi sau erasure.

## 3. Định nghĩa subsignature và chiều quan hệ

Gọi `sig(m)` là chữ ký phương thức `m` trong Java và `erasure(sig(m))` là chữ ký sau xóa kiểu.

**Chữ ký của `m1` là subsignature của `m2` nếu và chỉ nếu xảy ra một trong hai trường hợp:**

1. `sig(m1)` **giống** `sig(m2)` theo quy tắc chữ ký Java; hoặc
2. `sig(m1)` **giống chữ ký đã xóa kiểu của `m2`**.

Nói gọn:

```text
m1 subsignature m2
⇔ sig(m1) == sig(m2)
   hoặc sig(m1) == erasure(sig(m2))
```

Dấu `==` ở sơ đồ trên biểu thị **tương đương chữ ký theo quy tắc Java**, không phải toán tử so sánh đối tượng hay phép so sánh chuỗi ký tự thông thường.

Điểm dễ bỏ sót: **subsignature có hướng**. Nếu `m1` là subsignature của `m2`, không thể tự động kết luận chiều ngược lại cũng đúng. Trường hợp cùng chữ ký thì hai chiều đều đúng; trường hợp chỉ bằng erasure thì có thể đúng duy nhất một chiều.

Ví dụ:

```java
// Phương thức m1:
void accept(java.util.List items);

// Phương thức m2:
void accept(java.util.List<String> items);
```

- `sig(m1) = accept(List)`.
- `sig(m2) = accept(List<String>)`.
- `erasure(sig(m2)) = accept(List)`.
- **m1 là subsignature của m2** vì chữ ký của m1 bằng erasure của m2.
- **m2 không là subsignature của m1**: `accept(List<String>)` không giống `accept(List)`, cũng không giống erasure của `accept(List)`.

Hai phương thức minh họa này **không được đặt cạnh nhau trong cùng một lớp**. Quan hệ subsignature hữu ích khi xét ghi đè giữa các khai báo ở những lớp/interface có quan hệ kế thừa.

### Override-equivalent khác subsignature như thế nào?

Hai chữ ký là **override-equivalent** nếu chữ ký thứ nhất là subsignature của chữ ký thứ hai **hoặc ngược lại**. Khái niệm này có tính đối xứng, khác với việc kiểm tra một chiều của subsignature.

Tuy nhiên, việc hai chữ ký override-equivalent **không tự động đảm bảo một phương thức thực sự ghi đè phương thức kia**. Java vẫn xét quan hệ kế thừa, phương thức có được kế thừa/hiện diện phù hợp, `static` hay instance, quyền truy cập, kiểu trả về tương thích, ngoại lệ checked và các quy tắc liên quan.

Ví dụ `static` có thể ẩn một phương thức `static` khác (*hiding*) thay vì override. Phương thức `private` ở lớp cha không được ghi đè theo cách phương thức instance được kế thừa. Một lớp cũng không thể override một phương thức `final`.

## 4. Vì sao Java có quy tắc subsignature?

Xét API cũ trước generics:

```java
// Phiên bản API cũ, minh họa:
class Library {
    void consume(java.util.List items) { }
}

class Client extends Library {
    @Override
    void consume(java.util.List items) { }
}
```

Sau này, tác giả thư viện muốn mô tả phần tử rõ ràng hơn:

```java
// Phiên bản Library đã được generic hóa:
class Library {
    void consume(java.util.List<String> items) { }
}
```

Chữ ký `Client.consume(List)` là subsignature của `Library.consume(List<String>)`, nên phương thức cũ ở `Client` vẫn có thể override phương thức được generic hóa. Đây là một khả năng hỗ trợ tương thích trong quá trình chuyển API cũ sang generics.

Chiều ngược lại **không tương đương**. Nếu lớp cha có `consume(List)`, còn lớp con cố khai báo `consume(List<String>)` thì chữ ký ở lớp con **không phải subsignature** của chữ ký lớp cha. Vì hai chữ ký có cùng erasure nhưng không ghi đè đúng, trình biên dịch thường báo `name clash`.

Có thể nhớ bằng bảng:

| Khai báo ở lớp cha | Khai báo ở lớp con | Kết quả |
| --- | --- | --- |
| `void f(List<String> x)` | `void f(List x)` | Có thể override nhờ subsignature theo erasure; raw type có hạn chế. |
| `void f(List x)` | `void f(List<String> x)` | Không phải override hợp lệ; `name clash`. |
| `<T> void f(T x)` | `void f(Object x)` | Có thể override vì `f(Object)` là erasure của `f(T)`. |
| `void f(Object x)` | `<T> void f(T x)` | Không phải chiều override hợp lệ; có thể `name clash`. |
| `<T> void f(T x)` | `<U> void f(U x)` | Cùng chữ ký sau điều chỉnh tên tham số kiểu; có thể override. |

Bảng xét tới quy tắc chữ ký, với giả định phương thức là instance và các yêu cầu override khác đều đáp ứng. Nó không biến raw type thành lựa chọn mặc định: bản thân `List` không có tham số kiểu nên giảm độ an toàn và có thể tạo cảnh báo `rawtypes`.

## 5. Chương trình Java 17: ghi đè hợp lệ và cầu nối

Đây là chương trình độc lập, thể hiện ba tình huống liên quan:

- Override phương thức generic bằng chữ ký đã xóa kiểu.
- Override phương thức nhận `List<String>` bằng `List` ở phía lớp triển khai.
- Ghi đè khi một lớp generic được chuyên biệt hóa, dẫn đến bridge method; đồng thời quan sát cầu nối cho kiểu trả về hiệp biến.

**Tệp `ErasureSignatureDemo.java`:**

```java
import java.lang.reflect.Method;
import java.util.List;

public class ErasureSignatureDemo {
    static class Base {
        public <T> String render(T value) {
            return "base:" + value;
        }
    }

    static final class LegacyOverride extends Base {
        @Override
        public String render(Object value) {
            return "legacy:" + value;
        }
    }

    interface Catalog {
        void add(List<String> names);
    }

    static final class RawCatalog implements Catalog {
        @Override
        public void add(List names) {
            System.out.println("added:" + names.size());
        }
    }

    static class Box<T> {
        T echo(T input) {
            return input;
        }
    }

    static final class StringBox extends Box<String> {
        @Override
        String echo(String input) {
            return "str:" + input;
        }
    }

    static class Animal {
        Animal copy() {
            return this;
        }
    }

    static final class Dog extends Animal {
        @Override
        Dog copy() {
            return this;
        }
    }

    public static void main(String[] args) {
        Base base = new LegacyOverride();
        System.out.println(base.render(42));

        new RawCatalog().add(List.of("A", "B"));

        Box<String> box = new StringBox();
        System.out.println(box.echo("Java"));

        for (Method method : StringBox.class.getDeclaredMethods()) {
            if (method.isBridge()) {
                System.out.println("bridge:" + method.getName()
                    + "(" + method.getParameterTypes()[0].getSimpleName()
                    + ")->" + method.getReturnType().getSimpleName());
            }
        }

        Animal animal = new Dog();
        System.out.println(animal.copy().getClass().getSimpleName());

        for (Method method : Dog.class.getDeclaredMethods()) {
            if (method.isBridge()) {
                System.out.println("covariant bridge:" + method.getName()
                    + "()->" + method.getReturnType().getSimpleName());
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 ErasureSignatureDemo.java
java ErasureSignatureDemo
```

**Stdout đã kiểm chứng:**

```text
legacy:42
added:2
str:Java
bridge:echo(Object)->Object
Dog
covariant bridge:copy()->Animal
```

Chương trình dùng Java 17 trở lên. Với `javac --release 17 -Xlint:rawtypes ErasureSignatureDemo.java`, trình biên dịch cảnh báo một raw type tại tham số `List names` ở `RawCatalog`; đó là điều **có chủ đích để minh họa tương thích API cũ**. Trong ứng dụng mới, ưu tiên viết `void add(List<String> names)` đúng với interface nếu bạn không cần chứng minh cơ chế subsignature.

### 5.1. Vì sao `LegacyOverride.render(Object)` ghi đè được?

Ở `Base`, `render` là **phương thức generic**:

```java
public <T> String render(T value)
```

Type variable `T` không có bound tường minh, nên erasure của tham số `T` là `Object`. `LegacyOverride.render(Object)` có chữ ký bằng erasure của phương thức lớp cha, tức là subsignature của nó. Vì thế `@Override` hợp lệ, và lời gọi qua biến `Base` vẫn thực thi mã lớp con:

```text
legacy:42
```

Không cần tạo bridge chỉ để kết nối hai chữ ký này: chữ ký mã máy liên quan đã sử dụng tham số `Object`. Các giá trị trả về ở đây đều là `String`.

### 5.2. Vì sao `RawCatalog.add(List)` được chấp nhận?

`Catalog.add(List<String>)` có erasure tham số là `List`. Chữ ký `RawCatalog.add(List)` đúng bằng erasure đó, nên được phép override. Khi chạy, method in kích thước danh sách là `2`.

`RawCatalog` minh họa việc một mã cũ dùng raw `List` có thể tiếp tục đáp ứng hợp đồng được bổ sung generic. Raw type có thể cho phép các thao tác phần tử không an toàn ở mã triển khai; subsignature **không tự xác thực dữ liệu bên trong List** và không loại bỏ cảnh báo compiler.

### 5.3. Vì sao `StringBox.echo(String)` cần bridge?

`Box<T>` có phương thức `T echo(T)`. Trong ngữ cảnh `StringBox extends Box<String>`, kiểu `T` được thay bằng `String` để kiểm tra override ở mã nguồn, nên `String echo(String)` ghi đè hợp lệ.

Nhưng khi dịch `Box<T>`, erasure của `T` là `Object`. JVM vẫn có thể gọi `Box.echo(Object)` thông qua biến kiểu `Box<String>`. Trình biên dịch vì thế tạo một phương thức **bridge**, thường có dạng logic tương đương:

```java
// Minh họa cơ chế cầu nối do javac tự sinh, KHÔNG tự chép vào StringBox:
Object echo(Object input) {
    return echo((String) input);
}
```

Bridge mang descriptor đã xóa kiểu, ép đối số về `String` rồi chuyển lời gọi tới `StringBox.echo(String)`. Kết quả chương trình in:

```text
str:Java
bridge:echo(Object)->Object
```

`Method.isBridge()` cho phép nhận diện bridge qua reflection. Phương thức bridge thường cũng được đánh dấu synthetic (`Method.isSynthetic()`); trong ví dụ này, `javap` xác nhận cờ `ACC_BRIDGE` và `ACC_SYNTHETIC`.

Quan trọng: **subsignature là một quy tắc trong quá trình xác định ghi đè ở cấp nguồn; bridge là mã do compiler sinh để giữ đúng hành vi sau erasure.** Không phải hễ có subsignature thì phải sinh bridge: hai ví dụ `render` và `add` phía trên ghi đè hợp lệ mà không cần một bridge tương ứng.

### 5.4. Bridge do kiểu trả về hiệp biến

`Dog.copy()` trả về `Dog` trong khi `Animal.copy()` trả về `Animal`. Kiểu trả về con hợp lệ theo quy tắc *covariant return*. Khi nhìn ở bytecode, descriptor có chứa kiểu trả về, nên compiler có thể tạo cầu nối:

```text
Dog.copy()    -> Dog
Dog.copy()    -> Animal  // bridge, mô tả dạng logic
```

Lời gọi qua biến `Animal animal = new Dog()` vẫn trả lại đối tượng Dog; chương trình in `Dog`. Đây là ví dụ quan trọng vì **bridge method không chỉ có thể xuất hiện từ generics**; kiểu trả về hiệp biến cũng có thể dẫn tới bridge.

## 6. Chữ ký Java và JVM descriptor khác nhau ở đâu?

Đặt hai khai báo:

```java
// Minh họa:
class Parent<T> {
    T get(T value) {
        return value;
    }
}

class Child extends Parent<String> {
    @Override
    String get(String value) {
        return value;
    }
}
```

Chúng hợp lệ nếu đặt trong cùng tệp theo dạng các lớp phù hợp. Ở mã nguồn, compiler biết `Parent<String>` nên thấy `Child.get(String)` override phương thức thừa kế chuyên biệt thành `String get(String)`.

Nhưng class file của `Parent` vẫn dùng kiểu đã xóa:

```text
Parent.get(T)
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;

Child.get(String)
  descriptor: (Ljava/lang/String;)Ljava/lang/String;

Child.get(Object)  // bridge thường được javac sinh
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
```

Descriptor JVM thể hiện các kiểu với ký hiệu nội bộ: `Ljava/lang/String;` là tham chiếu `String`, `Ljava/lang/Object;` là tham chiếu `Object`, chữ `V` cho kết quả `void`. JVM descriptor **gồm cả kiểu trả về**. Java source signature thì **không** dùng kiểu trả về để quyết định một overload khác.

Để kiểm tra chương trình phần 5 sau khi biên dịch:

```bash
javap -p -v ErasureSignatureDemo$StringBox
javap -p -v ErasureSignatureDemo$Dog
```

Trên shell Unix-like, hãy trích dẫn tên chứa dấu `$` để shell không coi đó là biến, ví dụ:

```bash
javap -p -v 'ErasureSignatureDemo$StringBox'
javap -p -v 'ErasureSignatureDemo$Dog'
```

Trên PowerShell, đặt tên này trong dấu nháy đơn như trên cũng an toàn. Nếu chỉ cần danh sách phương thức ở cấp source-like, có thể dùng `javap -p ...`; cờ `-v` mới hiển thị chi tiết descriptor, flags và metadata.

Đầu ra `javap -v` cho các phương thức liên quan trong `StringBox` (lược riêng những phần cần quan sát) bao gồm:

```text
java.lang.String echo(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;

java.lang.Object echo(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
  flags: (0x1040) ACC_BRIDGE, ACC_SYNTHETIC
```

Ở `Dog`, cũng có hai dạng `copy()`: một trả về `Dog`, một bridge trả về `Animal`. Đây là lý do không nên nhìn mỗi phương thức do người lập trình viết để suy đoán toàn bộ phương thức có thể xuất hiện qua reflection ở runtime.

**Lưu ý:** Thông tin generic được lưu bằng metadata `Signature` khi cần thiết, nhưng `Signature` không biến `List<String>` và `List<Integer>` thành hai descriptor JVM khác nhau. Java không hỗ trợ overload chỉ dựa trên đối số kiểu generic của cùng một lớp tham số sau erasure.

## 7. Name clash: cùng erasure nhưng không thể override

### Trường hợp A: hai overload chỉ khác đối số generic

**Tệp `ErasureOverloads.java` — cố ý không biên dịch:**

```java
import java.util.List;

public class ErasureOverloads {
    void log(List<String> a) {}
    void log(List<Integer> a) {} // Lỗi: trùng erasure
}
```

Lệnh:

```bash
javac --release 17 ErasureOverloads.java
```

Thông báo lỗi trọng tâm mà `javac` đưa ra:

```text
name clash: log(List<Integer>) and log(List<String>) have the same erasure
```

Cả hai bị xóa thành `log(List)`. Không có đủ khác biệt về kiểu tham số ở cấp đã xóa để biểu diễn chúng như hai overload Java độc lập. Cách giải quyết phù hợp tùy nhu cầu: đặt tên khác như `logStrings` và `logIntegers`, hoặc dùng **một** phương thức `log(List<T>)` có hợp đồng chung. Thêm một tham số thực sự khác kiểu đã xóa cũng làm chữ ký khác, nhưng đừng thêm tham số giả chỉ để lách lỗi nếu nó không có ý nghĩa thiết kế.

### Trường hợp B: đặt `List<String>` ở lớp con của API raw

**Tệp `WrongDirection.java` — cố ý không biên dịch:**

```java
import java.util.List;

class LegacyBase {
    void save(List items) {}
}

public class WrongDirection extends LegacyBase {
    @Override
    void save(List<String> items) {}
}
```

Lệnh:

```bash
javac --release 17 WrongDirection.java
```

Hai thông báo quan trọng:

```text
name clash: save(List<String>) in WrongDirection and save(List) in LegacyBase
have the same erasure, yet neither overrides the other
method does not override or implement a method from a supertype
```

Chiều subsignature bị đảo: `save(List<String>)` của lớp con **không** là subsignature của `save(List)` ở lớp cha. Nếu cần override API cũ, dùng `save(List)` đúng chữ ký kế thừa; nếu kiểm soát API cha và muốn tăng tính an toàn, hãy cân nhắc generic hóa chính hợp đồng cha sau khi đánh giá tác động tương thích.

### Trường hợp C: chuyên biệt hóa một phương thức generic tùy ý

**Tệp `GenericMethodClash.java` — cố ý không biên dịch:**

```java
import java.util.List;

class GenericBase {
    <T> void use(List<T> items) {}
}

public class GenericMethodClash extends GenericBase {
    void use(List<String> items) {}
}
```

Lệnh:

```bash
javac --release 17 GenericMethodClash.java
```

Thông báo lỗi trọng tâm:

```text
name clash: use(List<String>) in GenericMethodClash and
use(List<T>) in GenericBase have the same erasure,
yet neither overrides the other
```

`GenericBase.use` là **phương thức generic**: mỗi lời gọi của nó có thể lựa chọn T. Một phương thức con chỉ nhận `List<String>` không thể được xem là triển khai hợp đồng hoạt động với mọi T. Erasure của hai tham số đều là `List`, khiến xung đột trở thành lỗi biên dịch thay vì một overload độc lập.

**Phân biệt với generic ở cấp lớp:** trong `class Box<T> { T echo(T v); }`, `Box<String>` cố định T thành String **cho việc nhìn nhận phương thức kế thừa trong kiểu đó**. Vì vậy `StringBox.echo(String)` override hợp lệ, với bridge giải quyết sự khác nhau ở bytecode. Còn `<T> void use(List<T>)` ở `GenericBase` có T thuộc **riêng phương thức**, lớp con không được biến giao kèo “mọi T” thành “chỉ String”.

## 8. Cách nhận biết overload, override và name clash

Khi gặp hai phương thức cùng tên, hãy phân tích theo thứ tự:

1. **Đặt chúng vào đúng ngữ cảnh kiểu.** Xác định phương thức ở cùng lớp, ở lớp cha/lớp con, hay ở hai interface. Với generic cấp lớp, thay tham số kiểu theo quan hệ kế thừa trước khi so các phương thức ở cấp mã nguồn.
2. **So chữ ký nguồn.** Nếu cùng chữ ký, không thể là hai overload trong cùng lớp; ở quan hệ kế thừa có thể là override nếu những điều kiện khác thỏa mãn.
3. **Kiểm tra subsignature đúng chiều.** Muốn xét `mChild` override `mParent`, hỏi liệu chữ ký của **child** có giống chữ ký **parent** hoặc erasure của parent hay không.
4. **So erasure của từng tham số.** Nếu hai phương thức có cùng erasure nhưng không thể override theo luật Java, bạn có nguy cơ `name clash`.
5. **Kiểm tra điều kiện ghi đè bổ sung.** `static`/instance, `private`, `final`, khả năng truy cập, kiểu trả về tương thích và checked exceptions đều có thể làm khai báo không hợp lệ dù chữ ký đã phù hợp.
6. **Kiểm tra cách Java dịch sang bytecode khi cần.** Nếu phương thức chuyên biệt có descriptor khác phương thức được thừa kế sau erasure, compiler có thể thêm bridge để giữ dispatch đúng.

Bảng đối chiếu nhanh:

| Hai phương thức | Chữ ký nguồn | Erasure | Kết luận trong ngữ cảnh chỉ rõ |
| --- | --- | --- | --- |
| Cùng lớp: `f(List<String>)` và `f(List<Integer>)` | Khác | Trùng `f(List)` | `name clash`, không overload được. |
| Cùng lớp: `f(String)` và `f(Integer)` | Khác | Khác | Có thể overload. |
| Cha `f(List<String>)`, con `f(List)` | Khác | Trùng | Con có thể override nhờ subsignature một chiều. |
| Cha `f(List)`, con `f(List<String>)` | Khác | Trùng | `name clash`; không override. |
| Cha `<T> f(T)`, con `f(Object)` | Khác | Trùng | Con có thể override; `Object` là erasure của T không bound. |
| Cha `<T> f(T)`, con `<U> f(U)` | Cùng sau đổi tên type variable | Trùng | Có thể override nếu các quy tắc khác hợp lệ. |
| `Box<T>.echo(T)`, `Box<String>` có `echo(String)` | Phù hợp sau chuyên biệt hóa T | Descriptor có thể khác | Override hợp lệ; compiler có thể tạo bridge. |

Trong bảng, các chữ ký rút gọn như `f(List)` chỉ minh họa phần tham số; các điều kiện khác của method override vẫn áp dụng.

## 9. Các hiểu nhầm quan trọng

**Nhầm 1 — “Cứ có cùng erasure là override”.** Sai. Cùng erasure có thể là điều kiện dẫn tới `name clash`. Phải kiểm tra subsignature và các quy tắc override khác.

**Nhầm 2 — “Subsignature là quan hệ hai chiều”.** Sai. Với một khai báo raw và một khai báo parameterized, chiều raw → parameterized có thể đáp ứng tiêu chí bằng erasure; chiều ngược lại không mặc nhiên đúng.

**Nhầm 3 — “Hai phương thức khác kiểu trả về thì có chữ ký khác”.** Sai ở cấp nguồn Java. Kiểu trả về không tham gia chữ ký phương thức nguồn; quy tắc return-type-substitutability mới quyết định tính hợp lệ của override. Tuy vậy, descriptor JVM có chứa kiểu trả về, tạo điều kiện để compiler sinh bridge cho covariant return.

**Nhầm 4 — “Bridge là overload do người lập trình thêm”.** Không đúng. Bridge là phương thức do compiler sinh để duy trì nghĩa ghi đè ở bytecode. Không nên tự viết thủ công một phương thức có chữ ký erasure trùng với bridge dự kiến; điều này có thể gây xung đột hoặc phá vỡ hợp đồng.

**Nhầm 5 — “Đổi từ `List<String>` sang `List<Integer>` là overload hợp lệ”.** Không đúng: hai kiểu tham số hóa có cùng erasure. Có thể cần tên API khác hoặc một phương thức generic chung.

**Nhầm 6 — “Muốn sửa `name clash` thì cast sang raw List”.** Cast ở vị trí gọi không thay đổi chữ ký của hai khai báo đang xung đột. Phải sửa chữ ký/thiết kế phương thức.

**Nhầm 7 — “Không thấy bridge qua source nên JVM không có”.** Compiler có thể sinh bridge trong class file. Dùng `Method.isBridge()` hoặc `javap -p -v` để quan sát khi cần chẩn đoán.

## 10. Thực hành chẩn đoán bằng công cụ

Với trường hợp nghi ngờ sai override:

1. **Đặt `@Override`** ở phương thức instance lớp con. Nếu compiler báo không ghi đè, đừng bỏ annotation ngay; xem lại chữ ký, chiều subsignature và kiểu tham số sau khi thay generic của superclass.
2. Biên dịch với cảnh báo khi đụng API cũ: `javac --release 17 -Xlint:rawtypes -Xlint:unchecked File.java`. `rawtypes` cảnh báo raw type, `unchecked` cảnh báo các phép toán không được compiler chứng minh hoàn toàn an toàn.
3. Với `name clash`, ghi riêng hai chữ ký nguồn và erasure vào giấy hoặc bảng rồi kiểm tra chiều `child → parent`. Một thay đổi type argument như `List<String>` sang `List<Object>` thường **không** giải quyết đụng erasure.
4. Nếu override được chấp nhận nhưng hành vi dispatch khó hiểu, dùng `javap -p -v 'TênLớp$LớpCon'`, tìm `descriptor:` và `ACC_BRIDGE`/`ACC_SYNTHETIC`.
5. Với reflection, `getDeclaredMethods()` có thể trả về cả bridge. Nếu muốn xử lý **phương thức do tác giả khai báo**, bạn cần cân nhắc lọc `isBridge()` và `isSynthetic()` theo mục đích tool; đừng vô điều kiện lọc nếu đang phân tích ABI hoặc runtime dispatch.

Khi thiết kế API mới, ưu tiên kiểu tham số hóa đầy đủ như `List<String>`. Raw method override là một cơ chế tương thích cần hiểu, nhưng thường không phải cách viết mới mong muốn.

## 11. Tự kiểm tra

### Câu 1

`Class A` có `void put(List<String> xs)`; `Class B extends A` có `void put(List xs)`. Chữ ký nào là subsignature của chữ ký nào?

**Đáp án:** `B.put(List)` là subsignature của `A.put(List<String>)` vì bằng erasure của khai báo ở A. Với điều kiện override khác phù hợp, B override được A.

### Câu 2

Đảo lại: A có `void put(List xs)`, B có `void put(List<String> xs)`. Điều gì xảy ra?

**Đáp án:** B không override được A vì chữ ký parameterized không bằng chữ ký raw của A hay erasure của nó. Hai khai báo có cùng erasure; compiler báo `name clash`.

### Câu 3

Có thể viết `void show(List<String> xs)` và `void show(List<Long> xs)` làm hai overload trong cùng lớp không?

**Đáp án:** Không. Cả hai có erasure `show(List)`.

### Câu 4

`class Parent<T>` có `T id(T x)`. `class Child extends Parent<String>` khai báo `@Override String id(String x)`. Vì sao override hợp lệ nhưng có thể xuất hiện phương thức `id(Object)` khi xem bytecode?

**Đáp án:** Ở cấp nguồn, kiểu T của Parent được chuyên biệt hóa thành String khi xét Child. Ở cấp bytecode, Parent được dịch với erasure Object; compiler thêm bridge `id(Object)` để chuyển đến `id(String)` và duy trì dispatch.

### Câu 5

Phương thức trả về `String` và phương thức cùng tên, cùng tham số nhưng trả về `Object` có phải hai overload được không?

**Đáp án:** Không. Kiểu trả về không thuộc chữ ký nguồn Java; sự thay đổi kiểu trả về chỉ có thể hợp lệ trong quan hệ ghi đè tương ứng nếu đáp ứng quy tắc return-type-substitutability, hoặc do compiler sinh bridge ở bytecode.

### Câu 6

Có phải phương thức nào là subsignature của phương thức khác đều cần một bridge?

**Đáp án:** Không. `render(Object)` override `render(T)` trong ví dụ vẫn cùng descriptor sau erasure, nên không cần bridge riêng cho trường hợp đó. Bridge cần thiết ở những tình huống compiler phải duy trì phân phối phương thức giữa các descriptor JVM khác nhau.

## 12. Ghi nhớ

- **Signature Java**: tên và kiểu tham số (kèm quy tắc tham số kiểu phương thức); không dùng kiểu trả về hay `throws` để phân biệt overload.
- **Erased signature**: tên và kiểu tham số sau khi áp dụng erasure; `List<String>` và `List<Integer>` cùng trở thành `List`.
- **Subsignature**: chữ ký m1 bằng chữ ký m2 **hoặc** bằng erasure chữ ký m2; đây là quan hệ **có hướng**.
- **Override-equivalent**: subsignature đúng ở ít nhất một chiều; việc override thực tế còn phải đáp ứng luật kế thừa và kiểu trả về.
- **Name clash**: chữ ký trùng sau erasure nhưng không thể cùng tồn tại/ghi đè theo quy tắc Java.
- **Bridge method**: phương thức do compiler sinh để giữ dispatch đúng sau erasure hoặc khi có kiểu trả về hiệp biến; quan sát bằng `javap` và `Method.isBridge()`.

Hiểu đồng thời các quy tắc này giúp bạn giải thích chính xác vì sao compiler chấp nhận một override dùng chữ ký đã xóa kiểu, từ chối một phương thức trông có vẻ “chuyên biệt hơn”, và tạo bridge dù mã nguồn chỉ khai báo một phương thức ghi đè.
