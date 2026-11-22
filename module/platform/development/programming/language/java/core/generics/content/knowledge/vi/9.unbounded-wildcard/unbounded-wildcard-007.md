# Các vị trí cú pháp không cho phép wildcard trong Java Generics

## 1. Mục tiêu học tập

Dấu hỏi `?` trong Java Generics là **wildcard type argument**: nó biểu thị một đối số kiểu chưa được biết chính xác, ví dụ `List<?>`. Wildcard không phải tên của một kiểu độc lập, không khai báo ra biến kiểu mới và không thể thay thế `T` ở mọi vị trí.

Bài này tập trung vào những **vị trí cú pháp hoặc ngữ cảnh kiểu mà Java không cho phép wildcard**, cách đọc thông báo lỗi và cách thay thế cho đúng. Trọng tâm là wildcard không giới hạn `?`; khi cần thiết, bài cũng đối chiếu với `? extends T` và `? super T` để tránh suy luận sai.

Sau bài học, bạn có thể:

- Phân biệt khai báo tham số kiểu (`<T>`) với việc sử dụng đối số kiểu wildcard (`<?>`).
- Nhận ra các vị trí cấm wildcard trong khai báo, kế thừa, khởi tạo đối tượng và lời gọi generic.
- Hiểu các ngữ cảnh *chỉ* cho phép wildcard không giới hạn, đặc biệt `instanceof` và tạo mảng generic.
- Chọn cách sửa bằng kiểu cụ thể, `<T>`, diamond `<>`, hoặc tham chiếu `List<?>` tùy mục đích.
- Phân biệt lỗi **cú pháp/ngữ cảnh** với lỗi **thao tác không an toàn trên wildcard**.

## 2. Quy tắc nền tảng: wildcard là type argument, không phải type parameter

Xem hai khái niệm khác nhau:

```java
class Box<T> {             // T là type parameter: tên biến kiểu được khai báo.
    private final T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}

Box<String> named = new Box<>("Java"); // String là đối số kiểu cụ thể.
Box<?> unknown = named;                 // ? là đối số kiểu wildcard hợp lệ.
```

`Box<T>` định nghĩa một kiểu generic mới với tên `T`. Trong `Box<?>`, dấu `?` không định nghĩa tham số: nó chỉ nói rằng tham số thực tế của đối tượng `Box` có một kiểu nào đó nhưng tham chiếu hiện tại không biết kiểu đó.

Cú pháp tổng quát:

```text
Khai báo kiểu/phương thức generic:
  class Box<T> { ... }
  static <T> T identity(T value) { ... }

Sử dụng kiểu generic:
  Box<String> b1;      // Đối số kiểu cụ thể.
  Box<?> b2;           // Wildcard không giới hạn.
  Box<? extends Number> b3;  // Wildcard cận trên.
  Box<? super Integer> b4;   // Wildcard cận dưới.
```

**Quy tắc nhớ nhanh:** Nếu một chỗ cần **tên kiểu hoặc tên tham số kiểu** để chương trình tham chiếu lại, `?` không thể thay thế tên đó. Khi một chỗ cần **đối số kiểu của một kiểu generic được sử dụng**, wildcard có thể hợp lệ, nhưng vẫn có những hạn chế theo ngữ cảnh được trình bày dưới đây.

## 3. Không được dùng `?` để khai báo tham số kiểu

### 3.1. Khai báo class, interface, record và generic method

Các khai báo sau không hợp lệ:

```java
// class Box<?> { }                        // SAI
// interface Repository<?> { }             // SAI
// record Pair<?>(Object left, Object right) { }  // SAI
// static <?> void print(Object value) { }  // SAI
```

Danh sách tham số kiểu của khai báo phải có một định danh như `T`, `E`, `K`, `V` hoặc một tên khác hợp lệ. `?` không phải định danh và không thể đóng vai trò là type parameter.

Cách sửa:

```java
class Box<T> {
    T value;
}

interface Repository<E> {
    E find();
}

record Pair<T>(T left, T right) {}

class GenericMethods {
    static <T> T identity(T value) {
        return value;
    }
}
```

Đây là các khai báo minh họa, không phải một chương trình có `main`. Wildcard vẫn có thể **xuất hiện bên trong kiểu tham số hoặc kiểu trả về** của một phương thức, chẳng hạn `void print(List<?> values)`; điều bị cấm là dùng `?` **làm tên tham số kiểu**.

### 3.2. Không thể viết `?` độc lập như tên kiểu biến hay kiểu trả về

```java
// ? item;                    // SAI
// static ? first() { ... }   // SAI
// void accept(? value) { }   // SAI
// ?[] elements;              // SAI
```

`?` không phải một type name đứng riêng. Hãy bọc nó trong một kiểu generic ở nơi cho phép type argument:

```java
Object item;
List<?> elements;

static Object first(List<?> values) {
    return values.get(0);
}

static void accept(List<?> values) {
    System.out.println(values.size());
}
```

Lưu ý: `List<?>` là **một kiểu dùng được trong chữ ký**, còn riêng dấu `?` thì không.

### 3.3. Không đặt dấu `?` độc lập sau `extends` ở khai báo type parameter

```java
// class NumberBox<T extends ?> { }  // SAI: ? không phải một kiểu làm cận.
```

Khi muốn giới hạn `T` phải là kiểu số:

```java
class NumberBox<T extends Number> { }
```

Trong khi đó, wildcard hoàn toàn có thể nằm **bên trong một kiểu dùng làm cận**:

```java
class HasComparable<T extends Comparable<?>> { }
```

Đây là một điểm khác biệt quan trọng: `Comparable<?>` là một kiểu tham số hóa hợp lệ trong mệnh đề cận; bản thân dấu `?` đứng lẻ sau `extends` không phải kiểu hợp lệ.

Tương tự, cú pháp `<T super Number>` không phải cách khai báo cận dưới cho type parameter. Từ khóa `super` để diễn đạt cận dưới là một phần của wildcard type argument, ví dụ `List<? super Number>`.

## 4. Không dùng wildcard trong kiểu cha hoặc interface cha trực tiếp

Khi định nghĩa một class hoặc interface có quan hệ kế thừa, phần kiểu generic trực tiếp ở `extends`/`implements` **không được chứa wildcard**.

Các ví dụ không hợp lệ:

```java
class Parent<T> { }

interface Handler<T> {
    void handle(T value);
}

// class Child extends Parent<?> { }   // SAI
// class X implements Handler<?> {      // SAI
//     public void handle(Object x) {}
// }
// interface ChildHandler extends Handler<?> { }  // SAI
```

Khi thực hiện kế thừa, Java cần một parameterization phù hợp để định nghĩa hợp đồng thành viên được kế thừa. Wildcard diễn tả một loại đối số chưa biết ở **nơi sử dụng tham chiếu**, không phải một đối số thích hợp cho quan hệ cha trực tiếp được khai báo.

Các phương án đúng:

```java
class StringChild extends Parent<String> { }

class GenericChild<T> extends Parent<T> { }

class StringHandler implements Handler<String> {
    @Override
    public void handle(String value) {
        System.out.println(value);
    }
}

interface GenericHandler<T> extends Handler<T> { }
```

Bạn **vẫn được khai báo biến** `Parent<?>` để tham chiếu đến `Parent<String>` hoặc `Parent<Integer>`:

```java
Parent<?> view = new StringChild(); // HỢP LỆ.
```

Vấn đề nằm ở vị trí `extends/implements` của khai báo kiểu; không phải toàn bộ các kiểu `Parent<?>` đều bị cấm.

## 5. Không dùng wildcard làm type argument trong biểu thức `new` khởi tạo đối tượng

Hãy phân biệt **kiểu tham chiếu bên trái** và **kiểu đối tượng cần tạo bên phải**:

```java
List<?> view = new ArrayList<String>();  // HỢP LỆ
List<?> inferred = new ArrayList<>();     // HỢP LỆ: diamond
// List<?> wrong = new ArrayList<?>();    // SAI
```

Với biểu thức khởi tạo đối tượng `new ArrayList<...>()`, kiểu cần tạo phải được xác định bằng đối số kiểu cụ thể hoặc để trình biên dịch suy luận qua `<>` (diamond). Java không cho viết wildcard type argument trực tiếp ở vị trí đó.

`<>` và `<?>` khác nhau hoàn toàn:

| Cú pháp | Ý nghĩa | Có thể dùng ngay sau `new ArrayList`? |
| --- | --- | --- |
| `<String>` | Chọn `String` làm đối số kiểu | Có |
| `<>` | Diamond: yêu cầu trình biên dịch suy luận kiểu | Có |
| `<?>` | Tham chiếu đến đối số kiểu chưa biết | Không |
| `<? extends Number>` | Wildcard cận trên | Không |
| `<? super Integer>` | Wildcard cận dưới | Không |

Ví dụ sửa lỗi:

```java
// List<?> a = new ArrayList<?>();           // SAI
List<?> a = new ArrayList<Object>();         // ĐÚNG
List<?> b = new ArrayList<>();               // ĐÚNG
List<? extends Number> c = new ArrayList<Integer>(); // ĐÚNG
```

Đừng hiểu `List<?> view = new ArrayList<>()` là đối tượng thực sự được khởi tạo với kiểu `?`. Biến `view` có một kiểu nhìn ra bên ngoài là wildcard, trong khi việc khởi tạo vẫn chọn được một đối số kiểu cụ thể qua cơ chế suy luận.

Quy tắc này cũng áp dụng cho đối số kiểu tường minh của generic constructor trong biểu thức `new`; không dùng `?` để yêu cầu Java suy luận. Hãy để trình biên dịch suy luận hoặc truyền kiểu cụ thể phù hợp.

## 6. Không dùng wildcard ở danh sách type argument tường minh khi gọi generic method/constructor

Giả sử có:

```java
static <T> T identity(T value) {
    return value;
}
```

Lời gọi generic method được phép để trình biên dịch suy luận `T`, hoặc nêu **kiểu cụ thể**:

```java
String a = identity("Java");
String b = MyClass.<String>identity("Generics");
```

Trong đó `MyClass` tượng trưng cho class chứa phương thức `static identity`; đoạn code này chỉ minh họa cú pháp gọi, chưa phải file độc lập.

Wildcard không được viết vào danh sách type argument tường minh của lời gọi:

```java
// String x = MyClass.<?>identity("Java"); // SAI
// List<?> y = Collections.<?>emptyList();  // SAI
```

Có thể sửa bằng cách bỏ phần type argument tường minh hoặc chọn kiểu cụ thể:

```java
List<?> a = java.util.Collections.emptyList();
List<?> b = java.util.Collections.<String>emptyList();
```

Quy tắc tương tự tồn tại ở type argument tường minh của lệnh gọi constructor `this(...)` hoặc `super(...)`, và đối số kiểu tường minh trong method reference: wildcard không đóng vai trò loại kiểu được truyền tường minh cho một lời gọi generic. **`List<?> result` là hợp lệ**, nhưng **`Collections.<?>emptyList()` không hợp lệ**; hai vị trí mang ý nghĩa khác nhau.

## 7. Không dùng wildcard trong kiểu nhận dạng member của method reference

Method reference dạng `TypeName::method` có thể dùng với class/interface generic, nhưng **kiểu tham chiếu dùng để tìm phương thức** không được chứa wildcard type argument.

Ví dụ cách dùng thông thường:

```java
java.util.function.ToIntFunction<List<String>> size = List::size;
int count = size.applyAsInt(List.of("a", "b"));
```

Biểu thức `List::size` hợp lệ; đoạn sau minh họa trường hợp cấm:

```java
// ToIntFunction<List<String>> wrong = List<?>::size; // SAI
```

Nếu cần giữ danh sách với kiểu phần tử không xác định, hãy dùng lambda nhận tham số đã được định kiểu rõ ràng hoặc chọn method reference hợp lệ:

```java
java.util.function.ToIntFunction<List<?>> countAny = values -> values.size();
```

Không nên thêm `?` vào chữ ký type reference chỉ để thể hiện rằng mã không phụ thuộc kiểu phần tử. Lambda và khai báo biến kiểu `List<?>` đã truyền tải điều đó.

## 8. Hai ngữ cảnh đặc biệt: chỉ wildcard không giới hạn là an toàn

Một số vị trí **cho phép `List<?>`**, nhưng không cho phép biểu thức dùng một generic type không reifiable như `List<String>` hay `List<? extends Number>` trong những ví dụ phổ biến từ biến `Object`. Lý do là **type erasure**: JVM không lưu thông tin kiểu phần tử generic để kiểm tra chúng ở runtime.

### 8.1. `instanceof`

```java
Object value = List.of("a", "b");

boolean valid = value instanceof List<?>; // HỢP LỆ
// boolean wrong1 = value instanceof List<String>; // SAI
// boolean wrong2 = value instanceof List<? extends Number>; // SAI
```

`List<?>` là một **reifiable type** (kiểu có đủ thông tin cần thiết cho kiểm tra kiểu ở runtime); do đó `instanceof List<?>` kiểm tra được liệu đối tượng là một `List` hay không. Nhưng phép kiểm tra đó **không** chứng minh phần tử bên trong có kiểu cụ thể nào.

Ví dụ pattern matching trong Java 17 cũng hợp lệ:

```java
Object input = List.of("one");
if (input instanceof List<?> list) {
    System.out.println(list.size()); // 1
}
```

Một số biến thể `instanceof` từ JDK mới còn có quy tắc kiểm tra khả năng chuyển kiểu theo kiểu tĩnh của biểu thức. Trong tình huống phổ biến `Object input`, hãy chọn `List<?>` và kiểm tra phần tử riêng nếu cần, thay vì trông chờ JVM xác thực `List<String>`.

### 8.2. Tạo mảng

Không phải mọi mảng có thành phần generic đều bị cấm tạo. Khi thành phần là kiểu reifiable `List<?>`, cú pháp sau hợp lệ:

```java
List<?>[] groups = new List<?>[2]; // HỢP LỆ
groups[0] = List.of(1, 2);
groups[1] = List.of("A", "B");
```

Đối chiếu:

```java
// List<String>[] a = new List<String>[2];              // SAI
// List<? extends Number>[] b = new List<? extends Number>[2]; // SAI
// List<? super Integer>[] c = new List<? super Integer>[2];   // SAI
```

`List<String>` và các tham số hóa có wildcard giới hạn không thuộc loại reifiable dùng làm kiểu thành phần trong **biểu thức tạo mảng**. Ngược lại `List<?>` reifiable và được phép trong `new List<?>[2]`. Khai báo một **tham chiếu** `List<String>[]` có thể viết về mặt cú pháp, nhưng khác với việc trực tiếp tạo ra mảng đó.

Điều được cho phép cũng không có nghĩa array là cấu trúc tốt nhất cho dữ liệu generic. Mảng có covariance và kiểm tra kiểu runtime khác với generics; với dữ liệu tập hợp, `List<List<?>>` thường dễ dùng và tránh nhiều vấn đề liên quan đến mảng.

## 9. Không có class literal cho kiểu generic với wildcard

Trong Java, class literal mang dạng `Type.class`, nhưng không thể viết nó dựa trên tham số hóa generic:

```java
Class<?> listClass = List.class;  // HỢP LỆ
Class<?> stringClass = String.class; // HỢP LỆ

// Class<?> wrong1 = List<?>.class;     // SAI
// Class<?> wrong2 = List<String>.class; // SAI
```

Vì type arguments bị xóa ở runtime, `List<String>` và `List<Integer>` không có hai đối tượng `Class` riêng biệt. Hãy dùng `List.class` khi cần đại diện runtime của lớp/interface; biến nhận `Class<?>` lại là một **vị trí sử dụng wildcard hợp lệ**.

Ví dụ:

```java
Class<?> type = java.util.ArrayList.class;
System.out.println(type.getSimpleName()); // ArrayList
```

Khi thực sự phải mô tả đầy đủ `List<String>` ở runtime (ví dụ framework serialization), cần một biểu diễn kiểu khác như `java.lang.reflect.ParameterizedType` hoặc cơ chế type token của thư viện; `List<?>.class` không giải quyết được bài toán này.

## 10. Những vị trí wildcard hoàn toàn được phép

Tránh phản xạ sai kiểu “cứ thấy dấu `?` là lỗi”. Các cách dùng dưới đây đều hợp lệ:

```java
class WildcardUses {
    List<?> field;                           // Field.
    static List<?> shared;                   // Static field.
    List<List<?>> nested;                    // Generic lồng nhau.
    java.util.Map<String, ?> byName;         // Type argument thứ hai.
    Class<?> runtimeType = String.class;     // Class<?>.

    void consume(List<?> values) {           // Tham số.
        for (Object value : values) {
            System.out.println(value);
        }
    }

    List<?> readOnlyView() {                  // Kiểu trả về.
        return List.of(1, 2, 3);
    }
}
```

Ở mỗi ví dụ, `?` nằm **bên trong danh sách đối số kiểu của một kiểu generic đang sử dụng**. Nó không đứng một mình như `? value`, không xuất hiện ở đầu danh sách khai báo type parameter của class và không chiếm chỗ type argument tường minh của biểu thức `new`.

### 10.1. Wildcard không giới hạn không phải raw type

```java
List<?> safeView = List.of("a", "b");  // Generic còn được kiểm tra kiểu.
List raw = List.of("a", "b");         // Raw type, tránh dùng trong code mới.
```

`List<?>` vẫn giữ kiểm tra kiểu: trình biên dịch không cho `safeView.add("x")` vì kiểu phần tử chưa biết. Raw `List` bỏ qua một phần cơ chế generic và dễ dẫn đến unchecked warning. Không dùng raw type làm “cách sửa nhanh” cho wildcard bị cấm.

### 10.2. Lỗi thao tác trên wildcard khác lỗi vị trí cú pháp

```java
List<?> values = new java.util.ArrayList<String>();
Object item = values.isEmpty() ? null : values.get(0); // HỢP LỆ
// values.add("hello"); // KHÔNG HỢP LỆ về kiểm tra kiểu phần tử.
```

Trong đoạn này, `List<?>` **đặt đúng vị trí và hoàn toàn hợp lệ về cú pháp**; vấn đề là lệnh `add("hello")` không bảo đảm an toàn, vì danh sách thực tế có thể có kiểu phần tử khác `String`. `values.add(null)` hợp lệ về kiểm tra kiểu, nhưng implementation bất biến có thể từ chối thay đổi ở runtime.

Hai nhóm lỗi khác nhau dẫn đến cách sửa khác nhau:

- **Vị trí wildcard bị cấm:** đổi cú pháp/kiến trúc khai báo, ví dụ `<T>`, `new ArrayList<>()`, `Parent<String>`.
- **Wildcard ở vị trí hợp lệ nhưng bị hạn chế thao tác:** đổi cách dùng API, ví dụ chỉ đọc dưới dạng `Object`, thêm type parameter `<T>` để giữ liên hệ kiểu, hoặc chọn `? super T` nếu API cần nhận `T`.

## 11. Chương trình Java 17+ đầy đủ, chạy được

Lưu đoạn sau vào tệp **`WildcardSyntaxDemo.java`**:

```java
import java.util.List;

public class WildcardSyntaxDemo {
    static void show(List<?> values) {
        for (Object value : values) {
            System.out.print(value + " ");
        }
        System.out.println();
    }

    static <T> T first(List<T> values) {
        return values.get(0);
    }

    public static void main(String[] args) {
        List<?> words = List.of("Java", "Generics");
        Object firstWord = words.get(0);

        List<?>[] groups = new List<?>[2];
        groups[0] = words;
        groups[1] = List.of(1, 2);
        Object firstNumber = groups[1].get(0);

        Object candidate = groups[0];
        boolean isList = candidate instanceof List<?>;
        Class<?> type = List.class;

        System.out.println("word=" + firstWord);
        System.out.println("number=" + firstNumber);
        System.out.println("groups=" + groups.length);
        System.out.println("isList=" + isList);
        System.out.println("class=" + type.getSimpleName());
        System.out.println("first=" + first(List.of("OK")));
        show(words);
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac WildcardSyntaxDemo.java
java WildcardSyntaxDemo
```

Stdout:

```text
word=Java
number=1
groups=2
isList=true
class=List
first=OK
Java Generics 
```

Dòng cuối có **một khoảng trắng ngay sau chữ `Generics`** vì `System.out.print(value + " ")` được gọi cho từng phần tử trước `println()`. Chương trình cho thấy `List<?>` có thể làm tham số, làm kiểu biến, làm thành phần mảng, và được dùng trong `instanceof`. Đồng thời `<T>` là cách khai báo generic method; `Class<?> type = List.class` phân biệt kiểu biến với class literal.

## 12. Bảng tra nhanh: đúng, sai và cách thay thế

| Vị trí | Ví dụ | Kết quả | Cách viết đúng / lý do |
| --- | --- | --- | --- |
| Khai báo type parameter của class | `class Box<?> {}` | Sai | `class Box<T> {}` |
| Khai báo type parameter của method | `<?> void run()` | Sai | `<T> void run()` khi thực sự cần `T` |
| Kiểu biến độc lập | `? x;` | Sai | `Object x;` hoặc `List<?> x;` |
| Kiểu tham số độc lập | `void f(? x)` | Sai | `void f(Object x)` hoặc `void f(List<?> x)` |
| Cận type parameter | `<T extends ?>` | Sai | `<T extends Number>` |
| Wildcard nằm trong cận hợp lệ | `<T extends Comparable<?>>` | Đúng | `Comparable<?>` là một kiểu được dùng làm bound |
| Kiểu cha trực tiếp | `extends Parent<?>` | Sai | `extends Parent<T>` hoặc `extends Parent<String>` |
| Interface cha trực tiếp | `implements Handler<?>` | Sai | `implements Handler<String>` |
| Biểu thức khởi tạo object | `new ArrayList<?>()` | Sai | `new ArrayList<>()` hoặc `new ArrayList<String>()` |
| Type argument của lời gọi generic method | `Collections.<?>emptyList()` | Sai | `Collections.emptyList()` |
| Receiver type của method reference | `List<?>::size` | Sai | `List::size` hoặc lambda |
| Class literal | `List<?>.class` | Sai | `List.class` |
| `instanceof` với wildcard không giới hạn | `obj instanceof List<?>` | Đúng | Chỉ kiểm tra danh sách, không kiểm tra kiểu phần tử |
| `instanceof` từ biến `Object` với kiểu phần tử cụ thể | `obj instanceof List<String>` | Sai | Kiểm tra `List<?>` rồi kiểm tra dữ liệu |
| Tạo mảng wildcard không giới hạn | `new List<?>[2]` | Đúng | Thành phần `List<?>` reifiable |
| Tạo mảng generic có đối số cụ thể | `new List<String>[2]` | Sai | Dùng `new List<?>[2]` hoặc `List<List<String>>` |
| Kiểu field | `List<?> field;` | Đúng | `?` là type argument |
| Kiểu trả về phương thức | `List<?> get()` | Đúng | `?` nằm trong `List<...>` |
| Generic lồng nhau | `Map<String, List<?>> data;` | Đúng | Wildcard là đối số kiểu của `List` bên trong |

Lưu ý: bảng giả định các class/interface và biến liên quan đã được khai báo, import thích hợp. Những dòng `Sai` là các mảnh cú pháp để phân tích, không đưa trực tiếp vào một tệp Java đang cần biên dịch.

## 13. Bài tập phân loại và giải thích

Giả sử có `import java.util.*;` và đã định nghĩa `class Holder<T> {}`.

### Câu 1. Có được khai báo như sau không?

```java
// class Strange<?> {}  // (a)
// Holder<?> h = new Holder<String>(); // (b)
// Holder<?> h = new Holder<?>(); // (c)
```

**Đáp án:** (a) sai vì dấu `?` không thể là tên type parameter; (b) đúng vì wildcard là type argument ở kiểu tham chiếu; (c) sai vì wildcard không được dùng làm đối số kiểu trong biểu thức khởi tạo đối tượng. Thay (c) bằng `new Holder<>()` hoặc `new Holder<String>()`.

### Câu 2. Vì sao cách này sai?

```java
// class TextHolder extends Holder<?> {}
```

**Đáp án:** `extends` chỉ định kiểu cha trực tiếp. Trong ngữ cảnh này wildcard type argument bị cấm. Chọn kiểu cụ thể (`extends Holder<String>`) hoặc truyền theo type parameter của lớp con (`class TextHolder<T> extends Holder<T> {}`).

### Câu 3. Các phép kiểm tra hoặc khởi tạo mảng này có hợp lệ không?

```java
Object o = List.of(42);
boolean a = o instanceof List<?>; // (a)
// boolean b = o instanceof List<Integer>; // (b)
List<?>[] c = new List<?>[3]; // (c)
// List<Integer>[] d = new List<Integer>[3]; // (d)
```

**Đáp án:** (a) hợp lệ; (b) không hợp lệ với biến `Object` vì không thể kiểm tra type argument `Integer` ở runtime; (c) hợp lệ vì `List<?>` reifiable; (d) không hợp lệ vì generic array creation có thành phần `List<Integer>` không reifiable.

### Câu 4. Cách gọi phương thức sau sai ở đâu?

```java
// List<?> result = Collections.<?>emptyList();
```

**Đáp án:** Wildcard được phép ở kiểu biến bên trái, nhưng bị cấm trong danh sách type argument tường minh của generic method invocation bên phải. Sửa thành `List<?> result = Collections.emptyList();` hoặc `List<?> result = Collections.<String>emptyList();`.

### Câu 5. Wildcard có thể được đặt trong một bound hay không?

```java
class Sample<T extends Comparable<?>> {}
```

**Đáp án:** Có. `T` là tên type parameter, còn `Comparable<?>` là **một kiểu được sử dụng làm cận**. Đây không phải cú pháp sai `T extends ?`. Khi cần bảo đảm `T` so sánh với chính `T`, mô hình `T extends Comparable<T>` thường diễn đạt quan hệ chặt chẽ hơn.

## 14. Quy trình xử lý khi javac báo lỗi có dấu `?`

1. **Đọc vị trí lỗi trước:** dấu `?` nằm trong `List<?>` hay đang đứng riêng như `? x`?
2. **Xác định ngữ cảnh:** đang khai báo tham số kiểu, khai báo cha, tạo đối tượng, gọi generic method, viết method reference, `instanceof` hay tạo mảng?
3. **Nếu đang đặt tên type parameter**, thay `?` bằng `T`/`E`... và khai báo phạm vi sử dụng.
4. **Nếu đang dùng `new`**, chọn một type argument cụ thể hoặc diamond `<>`.
5. **Nếu đang khai báo kiểu cha trực tiếp**, nêu kiểu cụ thể hoặc tiếp tục truyền type parameter từ lớp con.
6. **Nếu là type argument tường minh của lời gọi**, thường bỏ phần `<...>` để suy luận, hoặc nêu kiểu cụ thể.
7. **Nếu là `instanceof` hoặc tạo mảng**, kiểm tra tính reifiable. `List<?>` khác `List<String>` và `List<? extends Number>`.
8. **Nếu wildcard đúng chỗ nhưng thao tác `add`, `set` vẫn lỗi**, đây là bài toán bảo đảm kiểu dữ liệu/capture, không phải cú pháp. Xem xét `<T>` hoặc wildcard cận phù hợp.

## 15. Nguồn đặc tả và kết luận

- [Java Language Specification 17, §4.5.1 — Type Arguments of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): wildcard là type argument và ngữ nghĩa cận.
- [Java Language Specification 17, §4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): vì sao `List<?>` khác `List<String>` khi kiểm tra runtime.
- [Java Language Specification 17, §4.11 — Where Types Are Used](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.11): tổng hợp các ngữ cảnh cấm wildcard và các ngữ cảnh đòi hỏi reifiable type.
- [Java Language Specification 17, §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): quy tắc về type argument và diamond trong `new`.

**Ghi nhớ:** `?` dùng để biểu thị *đối số kiểu chưa biết* trong một kiểu generic được sử dụng, chẳng hạn `List<?>`; nó không thay thế được type parameter `T`, không làm kiểu cha trực tiếp, không nằm trong `new ArrayList<?>()` hay `Collections.<?>emptyList()`. Riêng `List<?>` là kiểu reifiable nên `instanceof List<?>` và `new List<?>[n]` hợp lệ.