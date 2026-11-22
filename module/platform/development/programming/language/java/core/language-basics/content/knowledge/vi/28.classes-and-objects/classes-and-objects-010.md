# Đọc cú pháp generic như `List<String>` và ý nghĩa kiểm tra kiểu trong Java

## 1. `List<String>` được đọc như thế nào?

Trong Java, **generic** (*kiểu tổng quát*) cho phép lớp, interface và phương thức mô tả kiểu dữ liệu mà chúng xử lý thông qua **tham số kiểu** (*type parameter*). Khi viết:

```java
List<String> names;
```

ta có thể đọc là **“một danh sách có phần tử kiểu `String`”**.

- `List` là interface `java.util.List<E>`, dùng để biểu diễn một dãy phần tử có thứ tự và cho phép truy cập theo vị trí.
- `<String>` là **đối số kiểu** (*type argument*) cụ thể, thay cho tham số kiểu `E` trong khai báo `List<E>`. Dấu `< >` ở đây chỉ thông tin kiểu, không phải các toán tử so sánh nhỏ hơn/lớn hơn.
- `names` là **biến tham chiếu** có kiểu `List<String>`. Nếu chỉ khai báo mà chưa gán, biến cục bộ này chưa sử dụng được để đọc; nếu là một field thì giá trị mặc định là `null`.
- `List` là **interface**, nên thường khởi tạo bằng một lớp cài đặt, ví dụ `ArrayList`. Cần `import java.util.List;` và `import java.util.ArrayList;` hoặc viết tên đầy đủ.

```java
import java.util.ArrayList;
import java.util.List;

// Các dòng sau đặt trong phương thức hoặc khối khởi tạo:
List<String> names = new ArrayList<String>();
names.add("An");
names.add("Binh");
String first = names.get(0);  // "An"
```

Trên Java 7+, có thể dùng **diamond operator** `<>` ở vế phải để trình biên dịch suy luận đối số kiểu từ ngữ cảnh:

```java
List<String> names = new ArrayList<>();
```

Cú pháp này vẫn giữ kiểu phần tử là `String`; `<>` không có nghĩa danh sách nhận mọi kiểu. Trong Java 17, dùng `var names = new ArrayList<String>();` thì kiểu được suy luận là `ArrayList<String>`; còn `var names = new ArrayList<>();` thiếu ngữ cảnh kiểu mong muốn sẽ suy luận kiểu thành phần là `Object`. Không nên mặc định hai cách khai báo `var` này cho kết quả giống `List<String>`.

## 2. Kiểm tra kiểu khi biên dịch mang lại điều gì?

Với `List<String>`, các phương thức do `List<E>` khai báo được nhìn qua tham số kiểu `E = String`:

| Biểu thức | Kiểu hoặc kết quả | Ý nghĩa |
| --- | --- | --- |
| `names.add("Java")` | Hợp lệ, trả về `boolean` | Thêm một `String` |
| `names.get(0)` | `String` | Không cần ép kiểu thủ công tại mã nguồn |
| `names.set(0, "Kotlin")` | `String` | Thay phần tử và trả về phần tử cũ |
| `for (String s : names)` | Hợp lệ | Duyệt từng `String` |
| `names.add(123)` | **Lỗi biên dịch** | `Integer` không phải `String` |
| `Integer n = names.get(0)` | **Lỗi biên dịch** | Không thể gán giá trị kiểu `String` cho `Integer` |

Ví dụ độc lập trong phương thức:

```java
List<String> names = new ArrayList<>();
names.add("Java");
String name = names.get(0); // Hợp lệ

// names.add(123);          // LỖI: int autobox thành Integer, không phải String
// Integer x = names.get(0); // LỖI: get trả về String theo khai báo generic
```

Điểm quan trọng: **trình biên dịch phát hiện nhiều phép gán/thêm sai kiểu trước khi chương trình chạy**. Điều này giúp API tự diễn đạt kiểu dữ liệu mong đợi, giảm lỗi ép kiểu thủ công và làm mã dễ đọc.

Generics **không bảo đảm** nội dung trong một danh sách luôn hợp lệ nếu đã cố tình bỏ qua cảnh báo dùng *raw type*, thực hiện ép kiểu không được kiểm chứng, hoặc có mã tương tác qua API cũ. Vì vậy cần hiểu cả giới hạn ở runtime.

## 3. Cấu trúc khai báo generic: tham số kiểu và đối số kiểu

Có thể tự định nghĩa một lớp generic:

```java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Ở đây `T` là **tham số kiểu** của lớp `Box<T>`. Khi sử dụng:

```java
Box<String> textBox = new Box<>("Hello");
String message = textBox.get(); // message == "Hello"

Box<Integer> intBox = new Box<>(42);
Integer number = intBox.get();  // number == 42
```

`String` và `Integer` ở hai khai báo là **đối số kiểu** cụ thể. Trình biên dịch kiểm tra `Box<String>` theo `String`, `Box<Integer>` theo `Integer`.

Generic method khai báo tham số kiểu trước kiểu trả về:

```java
static <T> T first(List<T> values) {
    return values.get(0);
}

// String s = first(List.of("A", "B"));
// Integer n = first(List.of(10, 20));
```

Đây là đoạn minh họa nằm trong một lớp. Khi dùng, kiểu `T` có thể được suy luận từ đối số. `List.of(...)` là tiện ích tạo danh sách **không cho phép thay đổi cấu trúc/phần tử** (unmodifiable) trong các phiên bản Java hiện đại; nếu cần `add`, dùng `ArrayList`.

### Vì sao dùng `Integer` thay vì `int`?

Đối số kiểu của generic **phải là kiểu tham chiếu**, không phải kiểu nguyên thủy:

```java
List<Integer> numbers = new ArrayList<>();
numbers.add(10); // autoboxing: int -> Integer
int value = numbers.get(0); // unboxing: Integer -> int

// List<int> invalid = new ArrayList<>(); // LỖI cú pháp/kiểu
```

Nếu phần tử `Integer` là `null`, unboxing sang `int` có thể gây `NullPointerException`. Với dữ liệu số lớn và hiệu năng nhạy cảm, các mảng nguyên thủy hoặc `IntStream` đôi khi tránh được chi phí boxing, tùy bài toán.

## 4. `List<String>` không phải `List<Object>`

Dù `String` là kiểu con của `Object`, **`List<String>` không phải kiểu con của `List<Object>`**. Generic type argument mặc định có tính **bất biến** (*invariant*).

```java
List<String> words = new ArrayList<>();
words.add("Java");

// List<Object> objects = words; // LỖI BIÊN DỊCH
```

Nếu cho phép phép gán trên, biến `objects` có thể gọi `objects.add(123)` và đưa `Integer` vào một danh sách vốn được khai báo chứa `String`, phá vỡ an toàn kiểu của `words`. Trình biên dịch từ chối phép gán để tránh điều đó.

Tương tự, `List<Integer>` không tự chuyển thành `List<Number>`. Để mô tả một danh sách có kiểu phần tử chưa biết chính xác hoặc theo một giới hạn, Java dùng **wildcard**.

## 5. Đọc các cú pháp wildcard thông dụng

| Cú pháp | Đọc/diễn giải | Lưu ý |
| --- | --- | --- |
| `List<?>` | Danh sách có **kiểu phần tử chưa biết** | Đọc phần tử như `Object`; không thêm giá trị khác `null` |
| `List<? extends Number>` | Danh sách có kiểu phần tử nào đó là `Number` hoặc kiểu con | Phù hợp cho thao tác **đọc** số; không được thêm tùy ý `Integer` |
| `List<? super Integer>` | Danh sách có kiểu phần tử nào đó là `Integer` hoặc một kiểu cha của nó | Có thể **thêm** `Integer`; khi đọc an toàn nhất chỉ biết là `Object` |

Ví dụ:

```java
static double sum(List<? extends Number> values) {
    double total = 0;
    for (Number value : values) {
        total += value.doubleValue();
    }
    return total;
}

static void addDefault(List<? super Integer> values) {
    values.add(0); // Integer được chấp nhận
}
```

`sum` nhận `List<Integer>`, `List<Double>` hoặc các danh sách có phần tử là kiểu con thích hợp của `Number` mà không đánh mất an toàn kiểu. Tuy nhiên `List<? extends Number>` không cho phép tùy ý thêm một `Number`: danh sách thực tế có thể là `List<Integer>`. Với `List<? super Integer>`, việc thêm `Integer` là an toàn vì kiểu thực tế có thể là `Integer`, `Number` hoặc `Object`.

Quy tắc nhớ thường dùng là **PECS**: *Producer Extends, Consumer Super*. Dùng `extends` khi chủ yếu đọc dữ liệu kiểu `T` từ cấu trúc; dùng `super` khi cần ghi các giá trị kiểu `T` vào cấu trúc.

Các từ `extends`/`super` ở **wildcard bound** mô tả quan hệ giới hạn kiểu, không có nghĩa `List` đã kế thừa trực tiếp từ một lớp danh sách khác.

## 6. Ví dụ hoàn chỉnh Java 17+

Tạo tệp **`GenericListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GenericListDemo {
    static void printUppercase(List<String> values) {
        for (String value : values) {
            System.out.println("upper: " + value.toUpperCase());
        }
    }

    static int countNonEmpty(List<? extends CharSequence> values) {
        int count = 0;
        for (CharSequence value : values) {
            if (value.length() > 0) {
                count++;
            }
        }
        return count;
    }

    static void addLabel(List<? super String> destination) {
        destination.add("new");
    }

    static <T> T first(List<T> values) {
        return values.get(0);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("java");
        names.add("core");

        String firstName = names.get(0);
        System.out.println("first: " + firstName);
        System.out.println("size: " + names.size());
        printUppercase(names);

        names.set(1, "generics");
        System.out.println("updated: " + names);
        System.out.println("first generic: " + first(names));

        List<Integer> numbers = List.of(10, 20);
        int firstNumber = first(numbers);
        System.out.println("numbers: " + numbers);
        System.out.println("number first: " + firstNumber);
        System.out.println("nonempty: " + countNonEmpty(names));

        List<Object> destination = new ArrayList<>();
        addLabel(destination);
        System.out.println("destination: " + destination);

        List<?> unknown = names;
        Object value = unknown.get(0);
        System.out.println("unknown item: " + value);

        // names.add(42);               // Lỗi biên dịch nếu bỏ chú thích
        // List<Object> bad = names;     // Lỗi vì generic invariant
    }
}
```

Trong thư mục chứa tệp với **JDK 17 trở lên**, chạy trên PowerShell/CMD (Windows) hoặc bash/zsh (Linux/macOS):

```bash
javac -encoding UTF-8 GenericListDemo.java
java GenericListDemo
```

Kết quả stdout chính xác (lệnh `javac` thành công không in thông báo):

```text
first: java
size: 2
upper: JAVA
upper: CORE
updated: [java, generics]
first generic: java
numbers: [10, 20]
number first: 10
nonempty: 2
destination: [new]
unknown item: java
```

Giải thích: `names` chỉ nhận `String`; `first(names)` suy luận `T` là `String`, còn `first(numbers)` suy luận `T` là `Integer` (khi gán sang `int` có unboxing). `countNonEmpty` chấp nhận `List<String>` vì `String` thực hiện `CharSequence`. `List<?>` cho phép lấy phần tử dạng `Object`, dù không biết chính xác kiểu phần tử qua biểu thức có wildcard.

## 7. Type erasure: kiểm tra lúc biên dịch khác runtime

Java thực hiện generics chủ yếu qua **type erasure**: ở cấp bytecode/runtime, nhiều thông tin về đối số kiểu của các tham chiếu generic không được giữ dưới dạng một loại đối tượng riêng cho mỗi `T`. Trình biên dịch kiểm tra kiểu và có thể thêm những phép ép kiểu cần thiết vào mã sinh ra.

Vì vậy:

```java
List<String> a = new ArrayList<>();
List<Integer> b = new ArrayList<>();
System.out.println(a.getClass() == b.getClass()); // true
```

Hai đối tượng đều được tạo bởi lớp runtime `ArrayList`; không có một lớp runtime riêng `ArrayList<String>` và `ArrayList<Integer>` cho hai đối tượng này.

Các ví dụ sau **không hợp lệ**:

```java
Object value = new ArrayList<String>();
// if (value instanceof List<String>) { } // LỖI biên dịch
// List<String>[] arrays = new List<String>[2]; // LỖI tạo mảng generic
```

Có thể kiểm tra `value instanceof List<?>` ở nơi phù hợp, nhưng **không thể từ phép kiểm tra đó kết luận mọi phần tử đều là `String`**. Đừng nhầm generics là cơ chế JVM liên tục kiểm tra đối số kiểu `String` khi thêm vào mọi `List`: các kiểm tra thường diễn ra **ở biên dịch**, còn tính hợp lệ ở runtime phụ thuộc thao tác cụ thể và hệ thống kiểu đã bị xóa thông tin generic.

**Raw type** như `List list = new ArrayList();` bỏ phần kiểm tra kiểu generic và dễ làm mất an toàn:

```java
List raw = new ArrayList(); // raw type: javac có thể cảnh báo
raw.add(123);
List<String> strings = raw; // unchecked conversion: cảnh báo
// String text = strings.get(0); // ClassCastException khi chạy
```

Các đoạn dùng raw type ở trên chỉ để phân tích hành vi; **không nên áp dụng** trong code mới. Cảnh báo có thể quan sát khi biên dịch với `javac -Xlint:rawtypes -Xlint:unchecked`. Khi sử dụng API cũ, hạn chế phạm vi chuyển đổi không được kiểm tra và xác minh dữ liệu trước khi tin tưởng kiểu phần tử.

## 8. So sánh nhanh với mảng và các lỗi thường gặp

Mảng và generic list có các đặc điểm khác nhau:

- `String[]` có kích thước cố định và cho phép truy cập `array[i]`; `List<String>` là interface của danh sách, truy cập qua `get(i)` và có thể thay đổi kích thước tùy implementation.
- Mảng các kiểu tham chiếu có tính **hiệp biến**: `Object[] a = new String[2];` biên dịch được nhưng gán `a[0] = Integer.valueOf(1)` gây `ArrayStoreException` khi chạy.
- Generic `List<String>` có tính **bất biến** đối với đối số kiểu: `List<Object> a = new ArrayList<String>();` bị từ chối khi biên dịch, giúp tránh kiểu lỗi tương tự ngay từ đầu.
- `List<String>` là danh sách chứa tham chiếu `String`; bản thân đối tượng danh sách có thể là `ArrayList`, `LinkedList` hoặc implementation tương thích, tùy ngữ cảnh.
- **Không viết** `List<int>`: generic không nhận kiểu nguyên thủy, dùng `List<Integer>`.
- **Không viết** `List<String> names = new List<>();`: `List` là interface, cần implementation như `new ArrayList<>()`.
- **Không dùng** `List<Object>` để đại diện chung cho mọi danh sách generic: nếu chỉ cần đọc phần tử không biết kiểu, dùng `List<?>`; nếu có ràng buộc kiểu, chọn wildcard phù hợp.
- **Không hiểu nhầm** `List.of("a", "b")` là danh sách cho phép `add`: danh sách từ `List.of` không hỗ trợ chỉnh sửa; `add` sẽ gây `UnsupportedOperationException`.
- `List<String>` **không tự đảm bảo phần tử khác `null`**: với `ArrayList<String>`, `null` có thể được thêm vào; gọi phương thức trên phần tử ấy cần kiểm tra. Ngoại lệ: một số factory/implementation như `List.of` không chấp nhận `null`.

## 9. Checklist đọc một kiểu generic

Khi gặp cú pháp như `Map<String, Integer>` hoặc `List<? extends Number>`, đọc lần lượt:

1. **Tên lớp/interface generic**: `Map`, `List`, `Box` xác định các thao tác có thể sử dụng.
2. **Đối số kiểu đặt trong `<...>`**: chẳng hạn `String`, `Integer` xác định các kiểu được kiểm tra khi biên dịch.
3. **Giới hạn kiểu nếu có**: `?`, `? extends T`, `? super T` diễn tả mức độ chắc chắn khi đọc/ghi dữ liệu.
4. **Lớp runtime thực tế**: `new ArrayList<>()` tạo đối tượng `ArrayList`; generic không tự tạo một lớp runtime chuyên biệt theo mỗi kiểu phần tử.
5. **Hoạt động hợp lệ**: `add`, `get`, `set` phải theo đúng kiểu và theo khả năng sửa đổi của implementation.

**Ghi nhớ:** `List<String>` nghĩa là danh sách có **hợp đồng kiểu phần tử `String` được trình biên dịch kiểm tra**. Generics giúp bắt lỗi sớm và giảm ép kiểu, trong khi wildcard mô tả cách dùng linh hoạt hơn và type erasure giải thích các giới hạn tại runtime.