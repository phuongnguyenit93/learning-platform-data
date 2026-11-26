# Khai báo trường, phương thức hỗ trợ và khởi tạo đối tượng trong tệp nguồn gọn

Compact source file cho phép đặt field, method và các kiểu thành viên trực tiếp trong tệp `.java`, không cần viết một khai báo `class` bao quanh. Trình biên dịch tạo một lớp ngầm định và xem những khai báo này như các thành viên của lớp đó. Nhờ vậy, chương trình nhỏ vẫn có thể có trạng thái, phương thức hỗ trợ và đối tượng riêng mà không phải bắt đầu bằng cú pháp lớp đầy đủ.

Tính năng Compact Source Files và Instance `main` Methods được chuẩn hóa trong Java 25 theo JEP 512. Tại ngày 25/11/2026, Java 25 là LTS mới nhất và JDK 27 là feature release mới nhất; cú pháp này vẫn được hỗ trợ trong Java SE 27. Các ví dụ trong bài dùng cú pháp final từ Java 25, không cần `--enable-preview`. Những vòng preview trước Java 25 chỉ được nhắc để nhận diện lịch sử.

Sau bài học, bạn có thể:

- Khai báo instance field và static field ở cấp tệp.
- Viết instance method và static method để chia nhỏ logic.
- Khởi tạo collection và object bằng field initializer.
- Hiểu thời điểm launcher tạo instance và thời điểm field được khởi tạo.
- Nhận biết giới hạn về constructor và initializer block của lớp ngầm định.

## 1. Các khai báo ở cấp tệp thuộc về một lớp ngầm định

Trong compact source file, những khai báo field, method, class và interface không nằm bên trong một class tường minh sẽ trở thành thành viên của một lớp ngầm định (*implicitly declared class*).

Ví dụ tối giản:

```java
String greeting = "Xin chào Java!";

void main() {
    System.out.println(greeting);
}
```

Field `greeting` và method `main` đều là thành viên của cùng một lớp ngầm định. Vì `main` là instance method, launcher tạo instance của lớp đó trước rồi mới gọi method. Bởi vậy, `main` có thể đọc trực tiếp field `greeting` mà không cần khai báo `static`.

Lớp ngầm định có một số đặc điểm cần nhớ:

- Là lớp top-level `final`, thuộc unnamed package và kế thừa `Object`.
- Tên lớp do môi trường biên dịch xác định; trong cách triển khai thông thường, tên thường dựa trên tên tệp bỏ phần mở rộng.
- Có default constructor không tham số do trình biên dịch tạo.
- Không thể tham chiếu lớp ngầm định bằng tên trong mã nguồn.
- Phải có ít nhất một candidate `main` method để chương trình có thể khởi chạy.

Compact source file không phải một ngôn ngữ riêng. Các field và method vẫn tuân theo quy tắc Java thông thường về kiểu, phạm vi, modifier, khởi tạo và truy cập thành viên.

## 2. Khai báo và khởi tạo field

Field khai báo trực tiếp trong compact source file hoạt động như field của một class bình thường. Bạn có thể dùng modifier như `private`, `protected`, `public`, `static` và `final`.

### Instance field

Instance field lưu trạng thái thuộc về instance được launcher tạo khi chạy instance `main`:

```java
private String owner = "Nhóm phát triển";
private int completedTasks = 0;
```

Method instance có thể đọc và cập nhật các field này trực tiếp:

```java
void markCompleted() {
    completedTasks++;
}

void printProgress() {
    System.out.println(owner + ": " + completedTasks + " công việc hoàn thành");
}
```

Không cần khai báo `static` cho field hoặc method chỉ được dùng trên instance hiện tại. Đây là cách phù hợp khi chương trình có trạng thái riêng và các helper method thao tác trên trạng thái đó.

### Static field

Static field thuộc về lớp ngầm định thay vì một instance cụ thể:

```java
private static final int MAX_RETRIES = 3;
private static int totalRuns = 0;
```

`MAX_RETRIES` là hằng số dùng chung. `totalRuns` là trạng thái cấp lớp và được chia sẻ giữa các instance của lớp trong cùng class loader. Static field được khởi tạo khi lớp được khởi tạo; instance field được khởi tạo mỗi khi một instance được tạo.

### Field initializer và thứ tự khởi tạo

Bạn có thể tạo object ngay trong biểu thức khởi tạo field:

```java
private final List<String> messages = new ArrayList<>();
private final LocalDate startedOn = LocalDate.now();
private final LocalDate reviewDate = startedOn.plusDays(7);
```

Các field instance được khởi tạo theo thứ tự khai báo trong tệp. Vì vậy `reviewDate` có thể sử dụng `startedOn` đã được khởi tạo trước đó. Field `static` được xử lý khi lớp được khởi tạo; field instance được xử lý khi instance được tạo.

`final` trên một field tham chiếu có nghĩa là không thể gán lại biến tham chiếu sau khi khởi tạo. Nó không tự làm object trở thành immutable. Ví dụ, `messages` không thể trỏ sang một `ArrayList` khác, nhưng vẫn có thể gọi `messages.add(...)` để thay đổi nội dung list.

Các kiểu như `List`, `ArrayList` và `LocalDate` thuộc module `java.base`. Compact source file tự động import theo nhu cầu các public top-level type trong những package được `java.base` export. Bạn vẫn có thể viết import tường minh để mã dễ đọc; các thư viện thuộc module khác vẫn cần được import và cấu hình module/classpath như bình thường.

## 3. Viết phương thức hỗ trợ

Method khai báo ở cấp tệp trở thành method của lớp ngầm định. Method instance có thể dùng trực tiếp field instance và gọi các method instance khác:

```java
private final List<String> names = new ArrayList<>();

private void addName(String name) {
    if (name == null || name.isBlank()) {
        return;
    }
    names.add(name.strip());
}

private void printNames() {
    for (String name : names) {
        System.out.println("- " + name);
    }
}

void main() {
    addName("Lan");
    addName("Minh");
    printNames();
}
```

Ở đây `addName` và `printNames` là helper method riêng của instance. Có thể thêm `private` để thể hiện chúng chỉ phục vụ nội bộ chương trình. Nếu không ghi access modifier, method có package access theo quy tắc Java thông thường.

Static method phù hợp với logic không cần trạng thái của instance:

```java
private static String normalizeCode(String code) {
    return code.strip().toUpperCase();
}
```

Static method không có `this` và không thể truy cập trực tiếp instance field. Nếu helper cần dùng `names` hoặc một field instance khác, hãy để nó là instance method.

## 4. Khởi tạo object và vòng đời của instance `main`

Compact source file thường dùng instance `main`, chẳng hạn:

```java
void main() {
    System.out.println("Chương trình bắt đầu");
}
```

Method này không cần `public`, không cần `static` và không cần tham số `String[]`. Khi launcher chọn instance `main`, quy trình khởi chạy diễn ra theo thứ tự:

1. JVM khởi tạo lớp và thực hiện các static field initializer.
2. Launcher tạo instance bằng default constructor không tham số do trình biên dịch cung cấp.
3. Các instance field initializer chạy theo thứ tự khai báo.
4. Launcher gọi instance `main` trên instance vừa tạo.
5. `main` gọi các helper method và sử dụng những object đã được tạo trong field initializer.

Nếu có cả `main(String[] args)` và `main()` đều phù hợp, launcher ưu tiên dạng có tham số `String[]`. Cả hai dạng có thể là static hoặc instance method; method được chọn phải có kết quả trả về `void` và đáp ứng quy tắc truy cập của launcher.

Ví dụ, khi cần dùng đối số dòng lệnh để tạo object, hãy khởi tạo object trong `main` hoặc helper được gọi từ `main`:

```java
void main(String[] args) {
    String userName = args.length == 0 ? "Guest" : args[0];
    UserSession session = new UserSession(userName);
    session.printWelcome();
}

private static final class UserSession {
    private final String userName;

    UserSession(String userName) {
        this.userName = userName;
    }

    void printWelcome() {
        System.out.println("Xin chào, " + userName);
    }
}
```

`UserSession` là member class được khai báo trong compact source file, nên nó có thể có constructor riêng. `new UserSession(userName)` tạo instance của kiểu trợ giúp đó và truyền dữ liệu vào constructor. Điều này khác với lớp ngầm định bao quanh các khai báo cấp tệp.

## 5. Ví dụ hoàn chỉnh: chương trình theo dõi công việc

Ví dụ sau kết hợp static field, instance field, nested record, instance `main` và helper method. Lưu mã vào `TaskBoard.java`:

```java
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;

private record Task(String title, LocalDate dueDate) {}

private static final int MAX_TASKS = 5;

private final String boardName = "Công việc cần làm";
private final List<Task> tasks = new ArrayList<>();
private final LocalDate createdOn = LocalDate.now();

void main(String[] args) {
    String owner = args.length == 0 ? "Bạn" : args[0];

    addTask(owner + " - đọc tài liệu", createdOn.plusDays(1));
    addTask(owner + " - ôn tập ví dụ", createdOn.plusDays(2));
    addTask(owner + " - hoàn thành bài tập", createdOn.plusDays(3));

    printBoard(owner);
}

private void addTask(String title, LocalDate dueDate) {
    if (tasks.size() >= MAX_TASKS) {
        System.out.println("Danh sách đã đạt giới hạn");
        return;
    }

    tasks.add(new Task(title, dueDate));
}

private void printBoard(String owner) {
    System.out.println(boardName + " của " + owner);
    System.out.println("Ngày tạo: " + createdOn);

    for (Task task : tasks) {
        System.out.println("- " + task.title() + " (hạn: " + task.dueDate() + ")");
    }

    System.out.println("Tổng số công việc: " + tasks.size());
}
```

Trong ví dụ:

- `MAX_TASKS` là static constant được chia sẻ ở cấp lớp.
- `boardName`, `tasks` và `createdOn` là instance field. Chúng được khởi tạo khi launcher tạo instance cho instance `main`.
- `Task` là nested record. `new Task(title, dueDate)` gọi canonical constructor do Java tạo cho record.
- `addTask` và `printBoard` là instance helper method, có thể truy cập trực tiếp các field của chương trình.
- `main(String[] args)` nhận dữ liệu từ command line và phối hợp các helper method.

Chạy trực tiếp bằng source launcher trên JDK 25 trở lên:

```bash
java TaskBoard.java "An"
```

Hoặc biên dịch rồi chạy:

```bash
javac TaskBoard.java
java TaskBoard "An"
```

Tên lớp được sinh cho compact source file là chi tiết do môi trường xác định; trong cách triển khai thông thường, tên dựa trên tên tệp. Không thể dùng tên lớp ngầm định đó trong một biểu thức Java như `new TaskBoard()` để tự tạo instance của chương trình.

## 6. Giới hạn về constructor và initializer block

Một khác biệt quan trọng so với class thông thường là compact source file không cho khai báo constructor, instance initializer block hoặc static initializer block cho lớp ngầm định.

Các khai báo sau không hợp lệ ở cấp tệp:

```java
// Không hợp lệ trong compact source file:
// TaskBoard() { ... }

// Không hợp lệ trong compact source file:
// { initializeDefaults(); }

// Không hợp lệ trong compact source file:
// static { loadConfiguration(); }
```

Lớp ngầm định luôn có default constructor không tham số do trình biên dịch cung cấp. Do đó:

- Dùng field initializer để tạo và gán giá trị ban đầu cho field.
- Gọi helper method ở đầu `main` nếu cần thực hiện nhiều bước khởi tạo theo thứ tự.
- Khai báo một member class hoặc record nếu cần kiểu dữ liệu trợ giúp có constructor riêng.
- Chuyển sang class tường minh nếu lớp chương trình cần constructor tùy biến, kế thừa, triển khai interface hoặc thuộc một named package.

Ví dụ, có thể viết:

```java
private final List<String> cache = new ArrayList<>();

void main() {
    initializeDefaults();
    runApplication();
}

private void initializeDefaults() {
    cache.add("ready");
}

private void runApplication() {
    System.out.println(cache);
}
```

Các câu lệnh trong `initializeDefaults()` chạy sau khi field initializer đã hoàn thành và sau khi launcher gọi `main`. Cách này phù hợp khi khởi tạo cần nhiều câu lệnh hoặc cần xử lý lỗi tường minh.

## 7. Khi nào nên chuyển sang class thông thường?

Compact source file phù hợp với chương trình nhỏ, công cụ dòng lệnh, ví dụ và prototype. Khi chương trình cần một API có thể được lớp khác tham chiếu, namespace riêng, constructor cho chính lớp chính, kế thừa hoặc quản lý dependency phức tạp, class thông thường sẽ rõ ràng hơn.

Có thể phát triển chương trình dần dần bằng cách bọc các khai báo cấp tệp (trừ các import) trong một khai báo class tường minh, rồi bổ sung package, constructor và các thành viên cần thiết. Field và helper method vẫn là thành viên Java thông thường sau khi chuyển đổi.

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Chương trình nhỏ có vài field và helper method | Compact source file. |
| Muốn instance `main` truy cập trạng thái mà không cần `static` | Compact source file hoặc class thông thường với instance `main`. |
| Cần constructor có tham số cho lớp chương trình | Class tường minh. |
| Cần public API để package khác sử dụng | Class tường minh trong named package. |
| Cần phân tách nhiều thành phần và quản lý vòng đời phức tạp | Các class/record/interface riêng, thường kết hợp build tool. |

## 8. Trạng thái tính năng trên các phiên bản Java

| Phiên bản | JEP | Trạng thái |
|---|---|---|
| Java 21 | JEP 445 | Preview lần đầu, tên cũ là Unnamed Classes and Instance Main Methods. |
| Java 22 | JEP 463 | Preview lần thứ hai. |
| Java 23 | JEP 477 | Preview lần thứ ba. |
| Java 24 | JEP 495 | Preview lần thứ tư. |
| Java 25 trở lên | JEP 512 | Final; Compact Source Files and Instance Main Methods là tính năng chính thức. |
| Java SE 27 | JEP 512 | Vẫn được hỗ trợ; tài liệu ngôn ngữ hiện hành mô tả cùng mô hình field, method và lớp ngầm định. |

Trong dự án hiện đại, dùng cú pháp final từ Java 25 trở lên. Không cần `--enable-preview` khi biên dịch hoặc chạy. Những ví dụ preview trước Java 25 chỉ có ý nghĩa khi đọc tài liệu lịch sử hoặc duy trì mã nguồn của đúng JDK preview tương ứng.

## 9. Kết luận

Compact source file cho phép khai báo field, helper method và kiểu thành viên trực tiếp trong tệp nguồn. Khi launcher gọi instance `main`, lớp ngầm định được tạo bằng default constructor không tham số; field initializer chạy trước `main`, nhờ đó chương trình có thể sử dụng trạng thái và object đã khởi tạo sẵn.

Hãy dùng instance field cho trạng thái của chương trình, static field cho dữ liệu cấp lớp, và helper method để chia logic. Nếu cần khởi tạo nhiều bước, gọi một method từ `main`; nếu cần constructor tùy biến cho một object trợ giúp, khai báo member class hoặc record. Lớp ngầm định của compact source file không có constructor hay initializer block do người viết khai báo. JEP 512 đã final từ Java 25 và vẫn được hỗ trợ trong JDK 27.

## Tài liệu tham khảo

- [JEP 512: Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512)
- [Oracle Java SE 25: Compact Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/25/language/compact-source-files-instance-main-methods.html)
- [Oracle Java SE 27: Compact Source Files and Instance Main Methods](https://docs.oracle.com/en/java/javase/27/language/compact-source-files-instance-main-methods.html)
- [Java Language Specification, Java SE 27 — §7.3 Compact Compilation Units](https://docs.oracle.com/javase/specs/jls/se27/html/jls-7.html)
- [Java Language Specification, Java SE 27 — §8.1.8 Implicitly Declared Classes](https://docs.oracle.com/javase/specs/jls/se27/html/jls-8.html#jls-8.1.8)
- [Oracle Java SE 25: Java Language Changes by Release](https://docs.oracle.com/en/java/javase/25/language/java-language-changes-release.html)
