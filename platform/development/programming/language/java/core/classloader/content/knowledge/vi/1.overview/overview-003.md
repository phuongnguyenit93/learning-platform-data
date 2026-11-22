# Phân biệt `ClassLoader`, `Class` và đối tượng của lớp trong Java

Trong Java, một **bộ nạp lớp** (class loader), một **đối tượng `Class`** và một **đối tượng được tạo từ lớp** là ba thực thể khác nhau. Chúng liên quan chặt chẽ, nhưng mỗi thực thể giải quyết một câu hỏi riêng:

- **`ClassLoader`:** JVM tìm, nạp và định nghĩa kiểu này bằng cách nào, trong không gian nạp lớp nào?
- **`Class<?>`:** Kiểu nào đang tồn tại ở thời điểm chạy, và JVM có thể kiểm tra hoặc phản chiếu thông tin nào về kiểu đó?
- **Instance (đối tượng của lớp):** Đây là thực thể cụ thể nào, với dữ liệu trạng thái riêng và danh tính riêng?

Hiểu đúng ba tầng này giúp giải thích vì sao một lớp có thể tạo nhiều đối tượng, vì sao hai lớp cùng tên đôi khi không tương thích kiểu, và vì sao việc lấy được `Class` chưa đồng nghĩa với việc đã tạo instance.

## 1. Mô hình tổng quan

```text
Nguồn định nghĩa kiểu (.class / bytecode / nguồn do loader cung cấp)
                         |
                         v
              ClassLoader / cơ chế nạp
                         |
            nạp + định nghĩa kiểu trong JVM
                         |
                         v
           Class<Sample> (mô tả kiểu lúc chạy)
                   /             \
                  /               \
                 v                 v
         new Sample()         new Sample()
                 |                 |
                 v                 v
            instance A         instance B
           (trạng thái A)     (trạng thái B)
```

Đây là mô hình khái niệm, không có nghĩa mỗi lần `new` đều đọc lại tệp `.class`. Sau khi kiểu đã được nạp/định nghĩa, các lần tạo đối tượng thông thường sử dụng định nghĩa kiểu đã có trong JVM.

| Góc nhìn | `ClassLoader` | `Class<?>` | Instance của lớp |
|---|---|---|---|
| Vai trò chính | Tìm, nạp, phối hợp định nghĩa lớp | Đại diện cho kiểu tại thời điểm chạy | Thực thể cụ thể của kiểu |
| Ví dụ biến | `ClassLoader loader` | `Class<Cat> type` | `Cat cat` |
| Cách thường lấy | `Cat.class.getClassLoader()` | `Cat.class`, `cat.getClass()`, `Class.forName(...)` | `new Cat()`, factory, reflection, deserialization… |
| Quan hệ số lượng | Một loader có thể phục vụ nhiều kiểu | Thông thường một `Class` cho mỗi định nghĩa kiểu được nạp | Một kiểu có thể có 0, 1 hoặc nhiều instance |
| Điều cần nhớ | Phân biệt **không gian định nghĩa lớp** | Phân biệt **kiểu runtime** | Phân biệt **danh tính và trạng thái từng đối tượng** |

Cả `ClassLoader` lẫn `Class<?>` đều là các **đối tượng Java** khi được biểu diễn bằng tham chiếu Java. Khác biệt ở đây là *vai trò*: `ClassLoader` là cơ chế nạp kiểu; `Class<?>` đại diện cho một kiểu; instance là đối tượng ứng dụng có kiểu đó. Bản thân một `ClassLoader` cũng có lớp runtime của nó, ví dụ `loader.getClass()`.

## 2. `ClassLoader`: ai nạp và định nghĩa lớp?

`ClassLoader` là lớp trừu tượng `java.lang.ClassLoader`, cùng với cơ chế loader tích hợp của JVM, tham gia quá trình tìm bytecode và biến bytecode thành định nghĩa lớp dùng tại thời điểm chạy.

Trong một ứng dụng Java thông thường có các tầng loader quen thuộc:

1. **Bootstrap loader** nạp các lớp nền tảng cốt lõi của Java. Nó được JVM thực hiện và không nhất thiết là một đối tượng `ClassLoader` Java thông thường; vì vậy `String.class.getClassLoader()` thường trả `null`.
2. **Platform class loader** phục vụ các lớp nền tảng trong môi trường mô-đun Java.
3. **Application/System class loader** thường phục vụ mã ứng dụng và thư viện trên classpath/module path phù hợp.

Các loader tùy biến có thể được dùng để nạp plugin, tách biệt phiên bản thư viện hoặc quản lý vòng đời mô-đun. Tuy vậy, **đừng mặc định một tên lớp luôn thuộc application loader**; kết quả phụ thuộc cách ứng dụng được chạy, cách đóng gói và loader thực tế.

### Nạp lớp khác với tạo đối tượng

Với lời gọi:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = loader.loadClass("com.example.Widget");
```

`loader.loadClass(...)` trả về một đối tượng `Class<?>` hoặc báo `ClassNotFoundException`. Nó **không tạo `new Widget()`**. `ClassLoader.loadClass(String)` cũng không mặc nhiên yêu cầu khởi tạo lớp (chạy static initializer). Đoạn mã trên là **mảnh minh họa**: nó chỉ thành công khi tên lớp tồn tại và loader nhìn thấy lớp đó.

Một loader có thể **ủy quyền** (delegate) cho loader cha. Cơ chế mặc định của `ClassLoader.loadClass` thường kiểm tra lớp đã nạp, nhờ cha nạp trước, rồi mới gọi `findClass` khi cần; loader tùy biến có thể có chính sách khác. Vì vậy loader mà bạn gọi `loadClass` có thể là *initiating loader*, trong khi định nghĩa lớp thực tế thuộc về một *defining loader* khác. Kết quả `type.getClassLoader()` biểu thị **defining loader**, không nhất thiết là biến `loader` được dùng để gọi.

### Tên lớp chưa đủ để xác định danh tính kiểu

Ở cấp JVM, danh tính của kiểu tham chiếu được xác định bởi **tên nhị phân của lớp + defining class loader**. Ví dụ:

```text
Loader A --defines--> com.example.Plugin  => Class<?> X
Loader B --defines--> com.example.Plugin  => Class<?> Y

Cùng tên "com.example.Plugin", nhưng X != Y nếu A và B
thực sự định nghĩa hai lớp riêng.
```

Hai instance sinh ra từ hai định nghĩa đó không tự động cast được cho nhau; có thể xuất hiện `ClassCastException` dù log in cùng tên lớp. Ngược lại, nếu hai loader con đều ủy quyền cho cùng một loader cha đã định nghĩa `com.example.Plugin`, chúng có thể cùng nhận **một** `Class`, không phải hai bản độc lập. Đây là lý do không nên kết luận chỉ dựa vào tên lớp hoặc số loader tham gia.

## 3. `Class<T>`: đại diện cho một kiểu tại runtime

`java.lang.Class<T>` là đối tượng phản chiếu đại diện cho **một kiểu trong JVM**. Nó cho phép truy vấn thông tin kiểu và thực hiện một số thao tác reflection.

```java
Class<String> stringType = String.class;
String text = "hello";
Class<? extends String> runtimeType = text.getClass();

System.out.println(stringType == runtimeType); // true
```

`String.class` và `text.getClass()` cùng trả về đại diện cho kiểu `java.lang.String`. Toán tử `==` ở đây so sánh chính **đối tượng Class**, không phải so sánh hai chuỗi hay hai instance.

Những cách lấy `Class` phổ biến:

| Cách | Ý nghĩa | Có tạo instance? |
|---|---|---|
| `SomeType.class` | Lấy `Class` của kiểu biết tại lúc viết code | Không |
| `someObject.getClass()` | Lấy kiểu runtime thực của đối tượng đang có | Không tạo instance mới |
| `Class.forName("pkg.SomeType")` | Tìm kiểu theo tên nhị phân qua cơ chế loader của caller; mặc định yêu cầu khởi tạo kiểu | Không |
| `Class.forName(name, false, loader)` | Tra cứu/nạp kiểu với loader chỉ định và không yêu cầu khởi tạo kiểu | Không |
| `loader.loadClass(name)` | Nhờ loader tìm/nạp kiểu | Không |

**Chú ý:** `Class` không chỉ đại diện cho những kiểu có thể `new`. Interface, abstract class, array, primitive và `void` cũng có đại diện `Class` (ví dụ `Runnable.class`, `int[].class`, `int.class`, `void.class`). Không thể suy ra chỉ vì tồn tại `Class<?>` thì luôn có thể gọi constructor để tạo đối tượng.

### Metadata của kiểu và trạng thái instance

Đối tượng `Class` cho phép truy vấn tên, modifier, superclass, interface, constructor, method, field, annotation… theo API reflection. Nó **không phải nơi giữ trạng thái instance riêng** của mỗi đối tượng.

Ví dụ nếu có hai `Person`, mỗi đối tượng có một trường `name` riêng, trong khi `first.getClass() == second.getClass()` vẫn đúng nếu cả hai được tạo từ cùng định nghĩa lớp. Các trường `static` thuộc về định nghĩa lớp tương ứng và được chia sẻ giữa các instance của chính định nghĩa lớp đó; không nên nhầm với trường instance hoặc coi `Class` là một instance `Person`.

### `Class` cũng là một đối tượng Java

`Class<?> type = Person.class;` có nghĩa **`type` tham chiếu đến một đối tượng của lớp `java.lang.Class`**, đại diện cho `Person`. Do đó:

- `type.getName()` cho tên kiểu đang được đại diện, ví dụ `com.example.Person`.
- `type.getClass()` trả về `Class` của bản thân đối tượng mirror, tức `java.lang.Class`.
- `type.getClassLoader()` trả về loader đã **định nghĩa `Person`**.
- `type.getClass().getClassLoader()` liên quan loader định nghĩa `java.lang.Class`, **không phải nhất thiết** loader của `Person`.

Đây là một trong những chỗ dễ nhầm nhất khi đọc log reflection.

## 4. Instance: một thực thể của kiểu

Với:

```java
Person first = new Person("An");
Person second = new Person("Binh");
```

`first` và `second` là **hai đối tượng riêng**, có thể chứa trạng thái khác nhau. Trong trường hợp cả hai được tạo từ cùng lớp runtime:

```java
first.getClass() == second.getClass()  // true
first == second                        // false
```

Hai biểu thức này trả lời hai câu hỏi khác nhau:

- **Có cùng kiểu runtime không?** So sánh `getClass()`.
- **Có trỏ cùng một đối tượng không?** So sánh tham chiếu `==`.

Cú pháp trên là **mảnh minh họa**, giả định `Person` có constructor nhận tên. `equals()` là quy tắc bình đẳng logic do lớp định nghĩa; nó không thay thế cho việc phân biệt danh tính object và danh tính `Class`.

`new Person(...)` đòi hỏi có một lớp cụ thể và constructor dùng được. JVM dùng định nghĩa kiểu tương ứng để cấp phát và khởi tạo instance. Một chương trình có thể tải hoặc tham chiếu `Person.class` mà chưa từng tạo bất kỳ `Person` nào.

## 5. Thí nghiệm Java 17+: ba thực thể trong cùng một chương trình

Tạo tệp **`LoaderClassObjectDemo.java`** với toàn bộ nội dung sau:

```java
public class LoaderClassObjectDemo {
    static class Sample {
        static {
            System.out.println("Sample initialized");
        }

        Sample() {
            System.out.println("Sample constructor");
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        // Lấy Class mà không tạo một Sample.
        Class<Sample> type = Sample.class;
        System.out.println("class literal captured");

        // Tìm cùng định nghĩa lớp, nhưng không yêu cầu initialize.
        Class<?> lookedUp = Class.forName(
                type.getName(), false, type.getClassLoader());
        System.out.println("same Class mirror: " + (type == lookedUp));

        ClassLoader definingLoader = type.getClassLoader();
        System.out.println("same loader: " +
                (definingLoader == LoaderClassObjectDemo.class.getClassLoader()));

        // Lần đầu tạo Sample: khởi tạo lớp, sau đó gọi constructor.
        Sample first = new Sample();
        Sample second = new Sample();

        System.out.println("same runtime Class: " +
                (first.getClass() == second.getClass()));
        System.out.println("runtime Class equals literal: " +
                (first.getClass() == type));
        System.out.println("same object: " + (first == second));
        System.out.println("isInstance: " + type.isInstance(first));
    }
}
```

Chạy với JDK 17 hoặc mới hơn:

```bash
javac LoaderClassObjectDemo.java
java LoaderClassObjectDemo
```

Kết quả chuẩn:

```text
class literal captured
same Class mirror: true
same loader: true
Sample initialized
Sample constructor
Sample constructor
same runtime Class: true
runtime Class equals literal: true
same object: false
isInstance: true
```

**Giải thích theo thứ tự:**

1. `Sample.class` lấy được `Class<Sample>` mà **chưa kích hoạt static initializer** của `Sample`.
2. `Class.forName(type.getName(), false, type.getClassLoader())` trả lại cùng định nghĩa `Sample`, với cờ `initialize=false`. Hai biến `type` và `lookedUp` vì thế cùng trỏ một `Class`.
3. `Sample` và lớp bao `LoaderClassObjectDemo` ở đây đều được định nghĩa qua cùng cơ chế nạp mã ứng dụng, nên phép so sánh loader trả `true`. Chương trình không phụ thuộc vào tên cụ thể của loader.
4. Lệnh `new Sample()` đầu tiên kích hoạt khởi tạo lớp `Sample` (in một lần `Sample initialized`), rồi gọi constructor. Lệnh `new` thứ hai chỉ chạy constructor; khởi tạo lớp không lặp lại cho cùng định nghĩa kiểu.
5. Hai instance khác nhau (`first == second` là `false`), nhưng đều tham chiếu đến cùng đối tượng `Class<Sample>`. `type.isInstance(first)` kiểm tra kiểu phù hợp, nên trả `true`.

Thí nghiệm cũng chỉ ra ba việc **lấy `Class`**, **khởi tạo lớp** và **khởi tạo một instance** là các sự kiện khác nhau.

## 6. Từ định nghĩa kiểu đến tạo đối tượng: hai vòng đời khác nhau

Định nghĩa lớp có vòng đời **loading → linking → initialization**; một đối tượng cụ thể lại có vòng đời **cấp phát → khởi tạo trường instance → chạy constructor**. Chúng liên quan nhưng không đồng nhất: lấy `Class<?>` không tự tạo instance; gọi `new` cần lớp tương ứng đã được khởi tạo khi cần và tạo một đối tượng mới.

| Quan sát | Kết luận đúng |
| --- | --- |
| `Target.class` hay `loader.loadClass(name)` trả `Class<?>` | Đã có đối tượng đại diện cho kiểu; không suy ra constructor instance hay `static {}` đã chạy |
| `Class.forName(name, true, loader)` | Yêu cầu khởi tạo kiểu nếu chưa khởi tạo; **không** tự tạo instance |
| `new Target()` lần đầu | JVM bảo đảm khởi tạo lớp theo quy tắc rồi tạo/khởi tạo **một instance** |
| `new Target()` lần tiếp theo | Tạo instance khác và chạy constructor tương ứng; initialization của cùng định nghĩa lớp thành công không lặp lại |

Ví dụ ở mục 5 cho thấy `Sample initialized` chỉ xuất hiện một lần, còn `Sample constructor` xuất hiện **hai lần**. Với lớp abstract/interface hoặc chỉ được tra cứu qua reflection, có thể tồn tại `Class<?>` mà chưa có instance nào. Để phân tích sâu verification, preparation, resolution và những trigger đặc biệt, cần phân biệt theo quy tắc của JVM; ở đây câu hỏi chính là **kiểu runtime có phải chính đối tượng nghiệp vụ không?**

## 7. Vì sao phân biệt đúng lại hữu ích?

### Tình huống A — Classpath/plugin báo `ClassNotFoundException`

Nếu `loadClass("com.example.Plugin")` không tìm thấy kiểu, đó là vấn đề ở quá trình **tìm/nạp tên lớp** qua loader hiện hành. Kiểm tra tên nhị phân, đường dẫn phân phối bytecode, module/classpath và loader được sử dụng. Việc thêm `new` hay cast không giải quyết được một kiểu chưa thể tìm thấy.

### Tình huống B — `ClassCastException` dù hai bên in cùng tên

Khi hai plugin mỗi bên có một loader định nghĩa riêng lớp cùng tên, kiểu runtime có thể khác nhau. Đọc `value.getClass().getName()` chỉ cho thấy tên, chưa đủ. Khi chẩn đoán, xem thêm **`value.getClass().getClassLoader()`** và `expectedType.getClassLoader()`, xác định loader nào thực sự định nghĩa kiểu. Thiết kế API chung nên đặt các interface hoặc DTO chia sẻ dưới loader chung có thể nhìn thấy từ cả hai phía.

### Tình huống C — Lấy `Class` nhưng constructor chưa chạy

`Class<?> type = SomeType.class;` không tự có instance. Khi dùng reflection, có thể gọi `getDeclaredConstructor(...).newInstance(...)` nếu kiểu cụ thể, constructor phù hợp và quyền truy cập cho phép. Việc tạo instance bằng reflection vẫn khác với việc tìm/nạp lớp; constructor có thể ném ngoại lệ, và reflection còn chịu ràng buộc truy cập/module. Đừng xem `Class.newInstance()` cũ là cách tạo đối tượng nên ưu tiên.

### Tình huống D — Dò loader của một đối tượng

Ví dụ:

```java
ClassLoader loaderOfType = instance.getClass().getClassLoader();
```

Đây là loader **định nghĩa kiểu runtime của `instance`**. Nếu `instance` là đối tượng `Class<?>`, cần quyết định muốn hỏi loader của **`java.lang.Class`** hay của **kiểu được đại diện**:

```java
Class<?> type = SomeType.class;
ClassLoader loaderOfSomeType = type.getClassLoader();
ClassLoader loaderOfClassMirror = type.getClass().getClassLoader();
```

Hai kết quả có thể khác nhau; kiểu `java.lang.Class` thuộc Java nền tảng, còn `SomeType` có thể thuộc loader ứng dụng.

## 8. Những hiểu nhầm phổ biến

**“Một tệp `.class` tương ứng đúng một `Class` trên toàn JVM.”** Không chính xác: cùng tên và bytecode có thể được định nghĩa tách biệt bởi những defining loader khác nhau. Trong cùng một định nghĩa lớp còn có nhiều instance.

**“Mỗi lần `new` JVM lại nạp lớp.”** Không đúng trong cách sử dụng thông thường: lớp được định nghĩa/lưu giữ để sử dụng lại, còn việc `new` tạo instance mới. Khi có loader khác định nghĩa lớp mới, đó là một định nghĩa runtime khác.

**“`ClassLoader` chính là `Class`.”** Sai: `ClassLoader` làm nhiệm vụ tìm/nạp/định nghĩa; `Class` là đại diện cho kiểu đã có. `ClassLoader.loadClass` trả về `Class<?>`, không trả instance ứng dụng.

**“`Class` chính là instance của kiểu nó đại diện.”** Sai: `Person.class` là một đối tượng `Class`, không phải `Person`. Nó không có giá trị của trường instance `name` của một `Person` cụ thể.

**“`getClassLoader() == null` nghĩa là lớp chưa nạp hoặc loader bị lỗi.”** Sai: với lớp bootstrap như `String`, `null` là dấu hiệu thường gặp cho bootstrap loader. Các loại đặc biệt như primitive/`void` không có loader do người dùng định nghĩa theo cách lớp thông thường.

**“`getClass()` và `instanceof` luôn cho cùng kiểu kiểm tra.”** Khác nhau: `getClass() == SomeType.class` kiểm tra **đúng kiểu runtime**, còn `instanceof SomeType` chấp nhận đối tượng có kiểu con/triển khai phù hợp. Với custom loaders, cả hai còn tuân theo danh tính kiểu mà JVM đã định nghĩa.

**“Loader là ranh giới bảo mật tuyệt đối.”** Không đúng: loader phục vụ nạp và cô lập danh tính kiểu, nhưng bản thân nó không thay thế sandbox, quản lý quyền truy cập hoặc kiểm soát mã không tin cậy.

## 9. Tự kiểm tra

**Câu 1.** `A a1 = new A(); A a2 = new A();` với cùng định nghĩa lớp. Biểu thức nào thường đúng: `a1 == a2` hay `a1.getClass() == a2.getClass()`?

**Đáp án:** Biểu thức thứ hai. Mỗi lần `new` tạo một đối tượng riêng, nhưng cả hai dùng chung đại diện cho cùng kiểu runtime.

**Câu 2.** Lệnh `Class<?> t = Class.forName("pkg.A", false, loader);` có tự gọi constructor `A()` không?

**Đáp án:** Không. Nó tìm/nạp kiểu (không yêu cầu khởi tạo lớp) và trả `Class<?>`; constructor instance chỉ chạy khi thực sự tạo đối tượng bằng cơ chế tương ứng.

**Câu 3.** Tại sao `com.example.Plugin` ở plugin X không cast được sang `com.example.Plugin` ở plugin Y dù cùng tên?

**Đáp án:** Nếu hai defining loader khác nhau đã định nghĩa hai lớp riêng, JVM xem chúng là hai kiểu runtime khác nhau. Cần thống nhất API/type chung ở loader chung hoặc truyền dữ liệu qua giao diện/cơ chế chuyển đổi thích hợp.

**Câu 4.** Tại sao `String.class.getClassLoader()` thường là `null`?

**Đáp án:** `String` do bootstrap loader nạp/định nghĩa; bootstrap không được biểu diễn bằng một instance `ClassLoader` Java giống như loader ứng dụng.

## 10. Ghi nhớ mô hình ba tầng

```text
ClassLoader  --nạp/định nghĩa-->  Class<?>  --được dùng khi tạo-->  Object
  (ai nạp?)                    (kiểu nào?)                    (thực thể nào?)
```

Khi gặp một lỗi runtime liên quan đến lớp, hỏi theo thứ tự: **tên và loader có định nghĩa đúng kiểu không? → `Class` runtime thực là gì? → đối tượng cụ thể nào đang được tạo hoặc truyền qua API?** Ba câu hỏi tách bạch thường dẫn đến nguyên nhân nhanh hơn việc chỉ nhìn tên lớp hay tên file `.class`.
