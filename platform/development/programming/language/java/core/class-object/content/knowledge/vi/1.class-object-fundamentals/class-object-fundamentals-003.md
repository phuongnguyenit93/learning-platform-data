# Lớp như một kiểu dữ liệu do người lập trình định nghĩa trong Java

## 1. Vì sao cần tự định nghĩa kiểu dữ liệu?

Một **kiểu dữ liệu (type)** cho biết một giá trị có ý nghĩa gì và chương trình có thể thực hiện những thao tác nào với giá trị đó. Java cung cấp các kiểu nguyên thủy như `int`, `boolean`, `double`, `char`; đồng thời cho phép người lập trình tạo **kiểu tham chiếu** mới bằng cách khai báo `class`.

Giả sử cần quản lý một khóa học. Chỉ dùng các biến rời rạc:

```java
String name = "Java";
int capacity = 2;
int enrolled = 0;
```

thì rất khó bảo đảm ba giá trị luôn thuộc về cùng một khóa học, và các quy tắc như “số học viên không vượt sức chứa” phải được kiểm tra ở nhiều nơi. Một lớp `Course` cho phép gom **trạng thái** (`name`, `capacity`, `enrolled`) và **hành vi** (`enroll()`, `summary()`) vào một đơn vị có tên và quy tắc rõ ràng.

```java
class Course {
    // Các trường, constructor và phương thức được khai báo tại đây.
}
```

Kể từ khi lớp được khai báo trong phạm vi truy cập phù hợp, `Course` cũng là một tên kiểu mà Java có thể sử dụng tương tự tên kiểu có sẵn `String`:

```java
Course course;         // Khai báo biến tham chiếu kiểu Course
Course[] courses;      // Khai báo biến tham chiếu tới mảng Course
```

Hai dòng trên **chỉ khai báo biến**, chưa tạo khóa học nào. Muốn tạo đối tượng, thông thường dùng `new Course(...)`.

> **Điểm cốt lõi:** `class` là bản khai báo một kiểu dữ liệu do người lập trình định nghĩa; **object** là một thể hiện (instance) được tạo từ lớp đó; **biến kiểu lớp** chứa tham chiếu có thể trỏ tới đối tượng phù hợp, hoặc có giá trị `null`.

## 2. Một lớp định nghĩa những gì?

Một khai báo lớp điển hình có dạng:

```java
class ClassName {
    // Fields: dữ liệu/trạng thái của mỗi đối tượng hoặc của lớp.
    // Constructors: thiết lập trạng thái ban đầu.
    // Methods: hành vi, thao tác và quy tắc.
}
```

| Thành phần | Vai trò | Ví dụ trong `Course` |
| --- | --- | --- |
| Tên lớp | Tạo một **tên kiểu** để dùng trong khai báo và kiểm tra kiểu | `Course` |
| Field (trường) instance | Lưu trạng thái riêng của mỗi đối tượng | `name`, `capacity`, `enrolled` |
| Constructor (hàm tạo) | Kiểm tra và khởi tạo đối tượng khi gọi `new`; cùng tên lớp, không có kiểu trả về | `Course(String name, int capacity)` |
| Instance method | Định nghĩa hành vi dựa trên trạng thái của đối tượng | `enroll()`, `summary()` |
| Access modifier | Giới hạn nơi được phép truy cập thành phần | `private` cho dữ liệu nội bộ, `public` cho API nếu cần |
| `static` member | Thuộc về lớp, không gắn với một instance cụ thể | Ví dụ `static int totalCreated` |

Lớp có thể không khai báo field, constructor hoặc method nào. Nếu không khai báo constructor nào, trình biên dịch cung cấp constructor mặc định không tham số với mức truy cập tương ứng với lớp; **khi đã tự khai báo một constructor, Java không tự bổ sung constructor không tham số**. Constructor khác phương thức thông thường: không có kiểu trả về (kể cả `void`), được gọi trong quá trình tạo đối tượng và không gọi như phương thức instance sau khi đã tạo đối tượng.

Dấu ngoặc nhọn xác định thân lớp; các lệnh thực thi như `System.out.println(...)` thường nằm bên trong method/constructor/initializer thích hợp, không đặt tùy ý trực tiếp trong thân lớp.

## 3. Ví dụ hoàn chỉnh: `Course` là một kiểu dữ liệu riêng

Tạo tệp **`CourseDemo.java`** với toàn bộ mã sau:

```java
class Course {
    private final String name;
    private final int capacity;
    private int enrolled;

    Course(String name, int capacity) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên khóa học không hợp lệ");
        }
        if (capacity <= 0) {
            throw new IllegalArgumentException("Sức chứa phải dương");
        }

        this.name = name;
        this.capacity = capacity;
        this.enrolled = 0;
    }

    boolean enroll() {
        if (enrolled == capacity) {
            return false;
        }
        enrolled++;
        return true;
    }

    String summary() {
        return name + ": " + enrolled + "/" + capacity;
    }
}

public class CourseDemo {
    static void printCourse(Course course) {
        System.out.println(course.summary());
    }

    public static void main(String[] args) {
        Course first = new Course("Java", 2);
        Course alias = first;
        Course second = new Course("Java", 2);

        System.out.println(first.enroll());
        printCourse(alias);
        System.out.println(first == alias);
        System.out.println(first == second);
        System.out.println(second.summary());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên (đứng tại thư mục chứa tệp):

```bash
javac CourseDemo.java
java CourseDemo
```

Kết quả chuẩn:

```text
true
Java: 1/2
true
false
Java: 0/2
```

Đọc ví dụ theo từng bước:

1. `class Course` khai báo kiểu `Course`. Mỗi đối tượng khóa học có dữ liệu riêng. `name` và `capacity` được đặt `final`, tức không được gán lại sau khi constructor hoàn tất; `enrolled` có thể thay đổi.
2. Constructor bảo vệ điều kiện đầu vào: tên phải có nội dung, sức chứa phải lớn hơn 0. `this.name = name` gán tham số `name` vào field `name` của **đối tượng đang khởi tạo**. Nếu không dùng `this`, hai tên trùng nhau có thể gây nhầm lẫn.
3. `new Course("Java", 2)` yêu cầu tạo một đối tượng mới, chạy constructor và trả về tham chiếu tới đối tượng đó. `first` mang **kiểu tĩnh `Course`**, nên trình biên dịch biết những phương thức `Course` cho phép gọi.
4. `first.enroll()` thay đổi trạng thái **đối tượng `first` trỏ tới** và trả về `true`; do đó `alias` cũng nhìn thấy `Java: 1/2` vì `alias = first` chỉ sao chép **tham chiếu**, không sao chép đối tượng.
5. `first == alias` là `true` vì hai tham chiếu trỏ tới cùng một đối tượng. `first == second` là `false` vì hai lần `new` tạo hai đối tượng khác nhau, dù dữ liệu ban đầu giống nhau.
6. `printCourse(Course course)` cho thấy `Course` được dùng làm **kiểu tham số phương thức**. `summary()` trả về `String`, cũng là một kiểu tham chiếu. `main` thuộc `CourseDemo` và dùng `static` để JVM có thể gọi nó theo điểm vào của chương trình.

Trong ví dụ có hai lớp top-level cùng tệp: `Course` không phải `public`, còn `CourseDemo` là `public`, nên tệp phải mang tên `CourseDemo.java`. Khi tổ chức dự án thực tế, thường đặt mỗi lớp top-level `public` trong tệp riêng cùng tên (ví dụ `Course.java` và `CourseDemo.java`); nếu dùng `package` thì cả hai tệp cần được đặt đúng cấu trúc nguồn của package đó.

## 4. Kiểu khai báo và khả năng kiểm tra lúc biên dịch

Hãy đọc `Course course = new Course("Java", 2);` như một **hợp đồng kiểu**, không chỉ là việc tạo một object: `Course` ở bên trái quyết định API mà compiler cho phép gọi qua biến `course`; biểu thức `new` ở bên phải tạo instance phù hợp và trả reference. Nếu chỉ viết `Course course;`, bạn mới **khai báo một biến**, chưa tạo khóa học; và biến cục bộ ấy phải được gán trước khi đọc.

Điểm riêng của bài này không phải đếm bao nhiêu biến đang trỏ cùng object (đó là bài phân biệt biến–instance), mà là **kiểu Course xuất hiện ở các ranh giới API**:

- `Course current` trong một parameter quy định loại giá trị mà caller được phép truyền.
- `Course create()` ở return type mô tả kết quả method hứa trả.
- `Course[]` hoặc `List<Course>` diễn đạt kiểu phần tử ở thời điểm biên dịch.
- `Object raw = new Course("Java", 2);` là phép gán hợp lệ, nhưng `raw.enroll()` **không** biên dịch: API của kiểu khai báo `Object` không có method `enroll`. Đối tượng thực vẫn là Course.

`null` là giá trị tham chiếu không trỏ tới object, không phải một Course rỗng. Mảng `new Course[3]` tạo **một mảng** với ba phần tử ban đầu null, không khởi tạo ba Course. Hai lưu ý này giúp tránh nhầm *kiểu phần tử* với *đối tượng phần tử*.

Khi cần phân biệt chính xác `class Person`, `Person p` và `new Person()`, hãy dùng phép truy vết riêng cho biến/instance; trong bài hiện tại, hãy thử viết một method nhận `Course` và kiểm tra compiler chấp nhận/từ chối những lời gọi nào.

## 5. Một lớp trở thành kiểu trong các vị trí nào?

Một lớp dùng được trong hầu hết vị trí cần một kiểu tham chiếu:

| Ngữ cảnh | Cách dùng | Ý nghĩa |
| --- | --- | --- |
| Biến cục bộ | `Course current = new Course("Java", 2);` | Biến tham chiếu chỉ nhận giá trị tương thích với `Course` |
| Tham số | `void print(Course current)` | Chỉ định loại đối tượng method chấp nhận |
| Kiểu trả về | `Course createCourse()` | Method hứa trả về tham chiếu kiểu tương thích |
| Field | `private Course favorite;` | Một đối tượng khác có thể lưu tham chiếu tới `Course` |
| Mảng | `Course[] courses = new Course[2];` | Mỗi phần tử có kiểu tham chiếu `Course`, ban đầu `null` |
| Tham số kiểu generic | `List<Course> courses` | Danh sách được kiểm tra kiểu phần tử `Course` khi biên dịch |
| Ép kiểu/kiểm tra kiểu | `value instanceof Course` | Kiểm tra tham chiếu có trỏ tới instance tương thích hay không |

Các dòng trong bảng là **mảnh mã minh họa**, không phải một chương trình chạy độc lập. Với `List<Course>` cần import `java.util.List` khi biên dịch trong chương trình thật.

Java dùng hệ thống kiểu theo **tên khai báo (nominal typing)**. Hai lớp có các field/method trông giống nhau không vì thế mà tự động trở thành cùng một kiểu. Ví dụ, `Course` và `Workshop` không thể gán cho nhau chỉ vì cả hai đều có `summary()`; phải có quan hệ kiểu hợp lệ như kế thừa một lớp chung hoặc triển khai cùng interface thì những phép gán phù hợp mới được phép. Điều này giúp trình biên dịch phát hiện sai cách sử dụng từ sớm.

Ví dụ mã **không hợp lệ và cố ý không biên dịch**:

```java
Course course = new Course("Java", 2);
course = 10; // LỖI BIÊN DỊCH: int không thể gán cho Course
```

Tên kiểu của biến cũng giới hạn thành phần nhìn thấy ở thời điểm biên dịch. Với `Object value = new Course("Java", 2);`, đối tượng thực tế là `Course` nhưng không thể gọi `value.enroll()` trực tiếp qua biến kiểu `Object`: method `enroll()` không được khai báo trong `Object`. Người học có thể gặp upcasting, downcasting và đa hình ở phần kế thừa; các chủ đề đó phát triển từ nguyên tắc kiểm tra kiểu này.

## 6. Thiết kế lớp để kiểu dữ liệu có ý nghĩa

Một kiểu người lập trình định nghĩa có ích khi nó **diễn đạt một khái niệm cụ thể** và **giữ đúng các quy tắc của khái niệm đó**.

### Đóng gói dữ liệu và hành vi

Nếu viết `public int enrolled;`, mã bên ngoài có thể trực tiếp gán `course.enrolled = -7` và phá vỡ quy tắc. Trong ví dụ, các field là `private`; lời gọi `enroll()` thay đổi dữ liệu thông qua kiểm tra `enrolled == capacity`. Đây là một lý do quan trọng để kết hợp trạng thái và hành vi trong cùng lớp, thay vì chỉ tạo một “túi biến”.

`private` giới hạn truy cập từ bên ngoài lớp; `public` làm thành phần có thể truy cập ở những nơi Java cho phép; không ghi modifier cho thành phần top-level hoặc member thông thường sẽ dùng phạm vi package-private. Có thêm `protected` trong thiết kế kế thừa. Phạm vi truy cập không thay đổi việc `Course` là một kiểu: nó quyết định **ở đâu** có thể đặt tên, tạo instance hoặc dùng member đó.

### Bất biến (invariant) và tính biến đổi

Một bất biến của `Course` là `capacity > 0` và `0 <= enrolled <= capacity`. Constructor tạo trạng thái hợp lệ; method `enroll()` duy trì bất biến qua mỗi lần gọi. `final` trên field `name`/`capacity` ngăn gán lại các field ấy sau khởi tạo; riêng `final` **không tự làm mọi đối tượng trở nên bất biến**. Nếu một field `final` tham chiếu đối tượng có thể sửa đổi, trạng thái bên trong đối tượng được tham chiếu vẫn có thể thay đổi.

Nếu muốn dữ liệu bất biến hoàn toàn, cần thiết kế không có đường sửa đổi trạng thái quan sát được; `record` có thể thuận tiện với các mô hình dữ liệu đơn giản, nhưng `record` có quy tắc riêng và không thay thế mọi lớp thông thường.

### Thành viên instance và `static`

`enroll()` và `enrolled` là thành viên **instance**: trạng thái gắn với từng khóa học. Một field hay method khai báo `static` thuộc về **lớp**. Ví dụ `Integer.parseInt("42")` được gọi qua tên lớp `Integer`; không cần tạo một instance `Integer` để thực hiện chức năng đó. Trong thiết kế `Course`, có thể dùng `static` cho một hằng số chung hoặc phương thức tiện ích không cần `this`.

Method `static` không có `this` và không thể truy cập trực tiếp field instance nếu thiếu tham chiếu tới một đối tượng cụ thể. Ngược lại, việc nhiều instance cùng có thể sử dụng một method không làm method đó trở thành `static`.

### Tên và trách nhiệm

Đặt tên lớp theo danh từ/khái niệm miền bài toán (`Course`, `Invoice`, `Coordinate`), theo thông lệ `UpperCamelCase`; method thường theo động từ hoặc yêu cầu thông tin (`enroll`, `summary`). Ưu tiên lớp có trách nhiệm rõ ràng; tránh gom nhiều khái niệm độc lập vào một lớp lớn. Kiểu dữ liệu tốt giúp người đọc hiểu ý nghĩa một tham số `Course` rõ hơn nhiều so với một nhóm biến `String`, `int`, `int` không có ngữ cảnh.

## 7. Từ mã nguồn đến kiểu được sử dụng khi chạy

Khi `javac CourseDemo.java` biên dịch ví dụ, nó kiểm tra cú pháp, kiểu, quyền truy cập và các lời gọi trong phạm vi mã biên dịch. Kết quả bình thường là hai tệp `Course.class` và `CourseDemo.class`. JVM nạp các định nghĩa lớp cần thiết khi chạy; chương trình bắt đầu từ `main(String[] args)` trong `CourseDemo`.

Phân biệt ba thứ có tên gần giống nhau:

- `Course`: **kiểu/lớp** do lập trình viên khai báo.
- `new Course("Java", 2)`: **đối tượng instance** được tạo khi chạy.
- `Course.class`: biểu thức tạo ra tham chiếu tới một đối tượng metadata kiểu `Class<Course>` mô tả lớp `Course`; bản thân metadata ấy **không phải một instance `Course`**.

Việc có tệp `Course.class` không đồng nghĩa JVM đã tạo một instance `Course`. Một lớp có thể được dùng cho kiểu tham số, field hoặc xử lý metadata mà chưa tạo object nào.

## 8. Lỗi phổ biến và cách nhận diện

| Nhầm lẫn | Vì sao sai / cách xử lý |
| --- | --- |
| “Khai báo `Course course;` là đã có khóa học” | Đây là khai báo biến tham chiếu; cần một giá trị hợp lệ trước khi đọc biến, thường từ `new Course(...)`. |
| “Hai biến kiểu `Course` là hai đối tượng” | `Course a = existing; Course b = a;` chỉ có thể cùng trỏ tới một đối tượng. |
| “Hai object cùng dữ liệu thì `==` là `true`” | `==` kiểm tra tham chiếu; phải thiết kế `equals()` nếu cần quan hệ bằng nhau theo miền bài toán. |
| “Gọi method trên `null` vẫn an toàn” | `null` không có đối tượng nhận lời gọi; có thể phát sinh `NullPointerException`. |
| “Để field `public` là cách đơn giản nhất” | Bên ngoài có thể phá bất biến; dùng quyền truy cập và method có kiểm tra khi trạng thái cần bảo vệ. |
| “`final Course x` làm đối tượng bất biến” | `final` trên biến tham chiếu chỉ ngăn **gán lại biến**; vẫn có thể gọi method làm thay đổi đối tượng được trỏ tới. |
| “Mọi field và method đều dùng qua tên lớp” | Chỉ thành viên `static` thuộc về lớp; thành viên instance cần đối tượng nhận lời gọi. |
| “Mọi constructor đều được Java tạo sẵn” | Constructor mặc định không tham số chỉ được sinh khi lớp không khai báo bất kỳ constructor nào. |
| “Tên file Java muốn đặt gì cũng được” | Lớp top-level `public` `CourseDemo` phải ở tệp `CourseDemo.java`. |
| “`new Course[3]` đã tạo ba Course” | Chỉ tạo mảng ba tham chiếu `null`; phải tạo từng `Course` khi cần. |

## 9. Tự kiểm tra mức độ hiểu

1. Từ `class Course` trong ví dụ, chỉ ra tên kiểu, ba field, một constructor và hai instance method. Vì sao `enroll()` cần truy cập trạng thái của đối tượng?
2. Nếu thêm `Course third = first; third.enroll();` ngay sau năm lệnh in của ví dụ, `first.summary()` sẽ là gì? **Đáp án:** `Java: 2/2`, vì `third` và `first` cùng tham chiếu một đối tượng; lần gọi `enroll()` thứ hai còn một chỗ.
3. Nếu tiếp tục gọi `first.enroll()` một lần nữa, method trả về gì và `enrolled` bằng bao nhiêu? **Đáp án:** trả về `false`, `enrolled` vẫn là `2`; invariant được bảo toàn.
4. Vì sao `Course c = null;` biên dịch được nhưng `c.summary()` khi chạy lại lỗi? **Đáp án:** kiểu tĩnh hợp lệ nhưng không có đối tượng thực để nhận lời gọi.
5. Hãy giải thích khác nhau giữa `Course`, `Course course`, `new Course(...)` và `Course.class` bằng một câu cho mỗi biểu thức.

**Ghi nhớ:** Định nghĩa một `class` là cách Java cho phép tạo một **kiểu tham chiếu mang tên và ý nghĩa do người lập trình quyết định**. Mỗi instance mang trạng thái riêng; biến kiểu lớp giữ tham chiếu; constructor và method giúp lớp kiểm soát cách đối tượng được tạo và sử dụng. Nhờ kiểm tra kiểu lúc biên dịch và đóng gói trạng thái cùng hành vi, các khái niệm nghiệp vụ trở thành thành phần chương trình rõ ràng, tái sử dụng được và khó dùng sai hơn.