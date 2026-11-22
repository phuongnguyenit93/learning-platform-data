# Từ chương trình chỉ có `main` tới chương trình có nhiều lớp — Java 17+

> **Java core — language-basics / Lớp và đối tượng**  
> **Yêu cầu:** JDK 17+, không dùng thư viện ngoài hoặc công cụ build.  
> **Mục tiêu:** Biết khi nào chương trình một `main` bắt đầu khó bảo trì; chuyển dữ liệu và hành vi liên quan vào lớp riêng; tạo đối tượng bằng `new`, gọi phương thức qua dấu chấm, biên dịch nhiều file `.java` và chạy đúng lớp có `main`.

## 1. Vì sao ban đầu chỉ cần một `main`?

Một chương trình Java rất nhỏ có thể đặt tất cả công việc trong `main`:

~~~java
public final class Hello {
    public static void main(String[] args) {
        String name = "Lan";
        System.out.println("Xin chào " + name);
    }
}
~~~

`main(String[] args)` là điểm bắt đầu quen thuộc khi chạy một lớp từ lệnh `java Hello`. Nó là phương thức `static`, vì Java launcher không cần tạo đối tượng `Hello` để gọi vào điểm bắt đầu này.

Khi ứng dụng chỉ thực hiện vài lệnh tuần tự, một `main` ngắn, rõ ràng là hợp lý. Nhưng nếu `main` vừa lưu dữ liệu, vừa kiểm tra hợp lệ, vừa tính toán, vừa in ra màn hình, các thay đổi sau này sẽ dễ làm ảnh hưởng nhiều phần khác nhau.

Bài này dùng cùng một yêu cầu đơn giản cho hai phiên bản:

- Có hai học viên: **Lan** đạt 7 điểm, **Minh** đạt 9 điểm.
- Cộng thêm 1 điểm cho Lan.
- In điểm từng người và điểm trung bình của lớp.

Kết quả của cả hai phiên bản phải **giống nhau**; mục tiêu của việc tách lớp là làm cấu trúc tốt hơn, không thay đổi nghiệp vụ.

## 2. Phiên bản đầu: tất cả logic nằm trong `main`

Tạo file **MainOnly.java**:

~~~java
public final class MainOnly {
    public static void main(String[] args) {
        String[] names = {"Lan", "Minh"};
        int[] scores = {7, 9};

        // Thay đổi điểm Lan.
        scores[0] += 1;

        // In điểm của từng học viên.
        for (int i = 0; i < names.length; i++) {
            System.out.println(names[i] + "=" + scores[i]);
        }

        // Tính và in điểm trung bình.
        int total = 0;
        for (int score : scores) {
            total += score;
        }
        System.out.println("average=" + (double) total / scores.length);
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 MainOnly.java
java MainOnly
~~~

**Expected stdout:**

~~~text
Lan=8
Minh=9
average=8.5
~~~

Cú pháp `(double) total / scores.length` bảo đảm phép chia ra kết quả thập phân; nếu dùng `int / int`, phép chia nguyên sẽ loại bỏ phần thập phân.

Phiên bản một lớp **không sai**. Nhưng khi cần thêm học viên, kiểm tra điểm từ 0 đến 10, lưu thông tin khác hoặc tái sử dụng cách tính trung bình ở nhiều nơi, những dòng mã này bắt đầu có vấn đề:

| Phần hiện tại | Vấn đề khi mở rộng |
| --- | --- |
| `names[i]` và `scores[i]` | Hai mảng song song phải luôn cùng độ dài, cùng vị trí |
| `scores[0] += 1` | Bất kỳ đoạn mã nào cũng có thể gán điểm ngoài giới hạn |
| Vòng lặp in điểm | Logic trình bày và xử lý dữ liệu nằm lẫn trong `main` |
| Phép tính trung bình | Dễ phải sao chép khi màn hình/chức năng khác cũng cần |
| Chỉ số `0` gắn với Lan | Thay thứ tự học viên có thể khiến thao tác đổi nhầm người |

Hướng cải thiện: gom **tên + điểm + quy tắc thay đổi điểm** thành một đối tượng `Student`; gom **danh sách học viên + tính trung bình + in danh sách** thành một đối tượng `Classroom`; giữ `main` ở lớp điều phối `SchoolApp`.

## 3. Nhận diện trách nhiệm của từng lớp

| Lớp | Trạng thái / vai trò | Hành vi chính |
| --- | --- | --- |
| `Student` | Tên và điểm của **một học viên** | Tạo học viên, đọc tên/điểm, tăng điểm có kiểm tra |
| `Classroom` | Các tham chiếu học viên trong **một lớp học** | In danh sách và tính điểm trung bình |
| `SchoolApp` | Điểm bắt đầu chạy chương trình | Tạo đối tượng, phối hợp lời gọi, in kết quả tổng hợp |

Cấu trúc thư mục đơn giản, mọi file nằm cùng một thư mục và **không khai báo `package`** trong ví dụ:

~~~text
study/
├── MainOnly.java      # Phiên bản một main để so sánh.
├── Student.java       # Đối tượng học viên.
├── Classroom.java     # Danh sách học viên và phép tính.
└── SchoolApp.java     # Main điều phối phiên bản nhiều lớp.
~~~

Có thể giữ `MainOnly.java` để học đối chiếu; khi chạy `SchoolApp`, JVM không tự chạy `MainOnly.main`.

Không phải cứ có nhiều lớp là chương trình “hướng đối tượng tốt”. Chỉ tách lớp khi lớp có **trách nhiệm rõ ràng**; tránh tạo những lớp chỉ chuyển tiếp một dòng lệnh mà không giúp mã dễ hiểu.

## 4. Tách một học viên thành `Student.java`

Tạo file **Student.java**:

~~~java
public final class Student {
    private final String name;
    private int score;

    public Student(String name, int score) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        if (score < 0 || score > 10) {
            throw new IllegalArgumentException("score must be 0..10");
        }
        this.name = name;
        this.score = score;
    }

    public String name() {
        return name;
    }

    public int score() {
        return score;
    }

    public void improve(int points) {
        if (points < 0 || points > 10 - score) {
            throw new IllegalArgumentException("invalid improvement");
        }
        score += points;
    }
}
~~~

Giải thích:

1. `class Student` tạo một **kiểu tham chiếu mới** tên `Student`. Mỗi lần `new Student("Lan", 7)` tạo một **đối tượng học viên** mới.
2. `private final String name` và `private int score` là **trường instance**. Mỗi đối tượng giữ giá trị riêng; mã lớp khác không truy cập trường `private` trực tiếp.
3. Constructor `Student(String name, int score)` kiểm tra đầu vào rồi khởi tạo trường qua `this.name = name` và `this.score = score`.
4. `name()`, `score()` và `improve(int points)` là **phương thức instance**; cần đối tượng nhận lời gọi, ví dụ `lan.improve(1)`.
5. `improve` bảo vệ quy tắc điểm không vượt 10. Dùng `points > 10 - score` thay vì `score + points > 10` để tránh phép cộng số nguyên lớn tràn trước khi kiểm tra.
6. `final` trên tên cấm thay **tham chiếu tên** sau khi khởi tạo. `score` không final vì nghiệp vụ cho phép tăng điểm. `final class Student` ở đầu cấm kế thừa lớp này; nó không tự làm mọi đối tượng Student bất biến.

Đặt logic kiểm tra trong lớp `Student` giúp các nơi sử dụng không phải lặp lại cùng quy tắc khi đổi điểm.

**Ví dụ lời gọi:** `Student lan = new Student("Lan", 7);` rồi `lan.improve(1);` và `lan.score()` trả `8`. Việc tạo `Student minh = new Student("Minh", 9);` không ảnh hưởng đối tượng `lan`.

## 5. Tạo `Classroom.java` để quản lý nhiều học viên

Tạo file **Classroom.java**:

~~~java
public final class Classroom {
    private final Student[] students;

    public Classroom(Student[] students) {
        if (students == null || students.length == 0) {
            throw new IllegalArgumentException("students must not be empty");
        }

        this.students = students.clone();

        for (Student student : this.students) {
            if (student == null) {
                throw new IllegalArgumentException("student must not be null");
            }
        }
    }

    public void printScores() {
        for (Student student : students) {
            System.out.println(student.name() + "=" + student.score());
        }
    }

    public double average() {
        int total = 0;
        for (Student student : students) {
            total += student.score();
        }
        return (double) total / students.length;
    }
}
~~~

`Classroom` dùng kiểu `Student[]` vì đã có lớp mô tả **một học viên**, không còn cần giữ hai mảng song song `String[]` và `int[]`. Nó tập trung vào hoạt động liên quan tới **cả lớp**.

- Constructor nhận một mảng `Student[]` và dùng `students.clone()` để **sao chép mảng ngoài**, tránh người gọi đổi vị trí các phần tử trong mảng đầu vào làm thay đổi danh sách bên trong.
- Các **đối tượng Student không được nhân bản** bởi `clone()` của mảng: hai mảng vẫn giữ tham chiếu tới cùng các đối tượng. Vì thế nếu `lan.improve(1)`, lớp học sẽ quan sát được điểm cập nhật.
- Vòng lặp kiểm tra không có phần tử `null` giúp `printScores()` và `average()` có thể gọi phương thức trên từng `Student`.
- `average()` không chia cho 0 vì constructor đã từ chối mảng rỗng.
- `printScores()` minh họa chức năng in cho bài học; trong ứng dụng có giao diện phức tạp, có thể tách phần hiển thị riêng và để `Classroom` trả dữ liệu.

`students` được khai báo `final` nghĩa là biến trường này không thể bị gán sang mảng khác sau khởi tạo, **không** có nghĩa mọi phần tử hoặc trạng thái `Student` đều bất biến.

## 6. `SchoolApp.java`: `main` chỉ điều phối các đối tượng

Tạo file **SchoolApp.java**:

~~~java
public final class SchoolApp {
    public static void main(String[] args) {
        Student lan = new Student("Lan", 7);
        Student minh = new Student("Minh", 9);

        Classroom classroom =
                new Classroom(new Student[] {lan, minh});

        lan.improve(1);
        classroom.printScores();

        System.out.println("average=" + classroom.average());
    }
}
~~~

Phiên bản này thực hiện đúng các bước của `MainOnly`, nhưng `main` không cần biết cách lưu điểm hay cách cộng điểm trung bình:

~~~text
SchoolApp.main(...)
   |
   +--> new Student("Lan", 7)
   +--> new Student("Minh", 9)
   +--> new Classroom(Student[] {lan, minh})
   |
   +--> lan.improve(1)
   +--> classroom.printScores()
   +--> classroom.average()
~~~

Trong `classroom.printScores()`, dấu chấm `.` biểu thị gọi **phương thức của đối tượng classroom**; tương tự `lan.improve(1)` gọi phương thức của đối tượng `Student` mà biến `lan` đang tham chiếu. `Student[]` là mảng chứa **các tham chiếu Student**, không phải một loại lớp học có tính năng in/tính trung bình tự động.

`SchoolApp.main` là `static` vì nó là điểm vào; nó **được phép tạo đối tượng và gọi instance method thông qua các tham chiếu**, chứ không phải vì `static` thì bị cấm mọi lời gọi phương thức instance.

## 7. Biên dịch và chạy chương trình nhiều lớp

Đặt `Student.java`, `Classroom.java` và `SchoolApp.java` cùng thư mục. Trong terminal đang đứng tại thư mục đó, dùng lệnh sau; tên file **phải** khớp tên lớp top-level `public`:

~~~bash
javac -encoding UTF-8 Student.java Classroom.java SchoolApp.java
java SchoolApp
~~~

**Expected stdout chính xác của `java SchoolApp`:**

~~~text
Lan=8
Minh=9
average=8.5
~~~

Kết quả **giống hệt `MainOnly`**. Biên dịch nhiều tệp tạo ra `Student.class`, `Classroom.class`, `SchoolApp.class` ở thư mục hiện hành. `javac` cần biết các lớp tham chiếu nhau; liệt kê đủ ba file như trên là cách đơn giản và rõ ràng cho người mới.

Có thể biên dịch vào thư mục riêng; tạo `out` trước và chạy tên lớp từ classpath root:

~~~bash
javac -encoding UTF-8 -d out Student.java Classroom.java SchoolApp.java
java -cp out SchoolApp
~~~

Ở lệnh này, **thư mục `out` phải tồn tại trước** khi truyền cho `javac -d`. Với Bash/Linux/macOS có thể tạo bằng `mkdir -p out`; với PowerShell: `New-Item -ItemType Directory -Force out | Out-Null`. Đây là lựa chọn để giữ tệp `.class` tách khỏi nguồn, không bắt buộc nếu đang dùng cặp lệnh đầu tiên.

**Lệnh `java SchoolApp` chọn đúng một điểm vào:** JVM không lần lượt chạy tất cả phương thức `main` của các lớp hiện diện. Nếu muốn chạy phiên bản cũ, dùng `java MainOnly` riêng (sau khi biên dịch `MainOnly.java`).

Ví dụ trên nằm trong **unnamed package** để tập trung vào sự chuyển đổi từ một sang nhiều lớp. Khi dự án lớn, tổ chức theo `package` và dùng `javac -d`/`java -cp` với **tên lớp đầy đủ**; việc chuyển sang package không làm thay đổi trách nhiệm các đối tượng.

## 8. Quan hệ đối tượng và biến tham chiếu sau khi tách lớp

Đoạn mã:

~~~java
Student lan = new Student("Lan", 7);
Student minh = new Student("Minh", 9);
Student[] list = {lan, minh};
Classroom room = new Classroom(list);
~~~

Có thể hình dung:

~~~text
lan -------> Student(name="Lan", score=7) <------ list[0]
                           ^
                           |
                      room.students[0]

minh ------> Student(name="Minh", score=9) <----- list[1]
                           ^
                           |
                      room.students[1]
~~~

`room.students` là mảng riêng do `clone()` tạo, nhưng các phần tử tham chiếu tới **cùng hai đối tượng Student**. Vì vậy:

- `lan.improve(1)` khiến `room.average()` dùng điểm Lan mới bằng 8.
- `list[0] = new Student("Hoa", 10)` **không tự thay** `room.students[0]` vì lớp học đã sao chép các vị trí của mảng đầu vào.
- `Student alias = lan; alias.improve(1)` tiếp tục sửa **cùng đối tượng Lan**; gán `alias = new Student(...)` chỉ đổi biến alias.
- Nếu truyền `null` thay mảng cho constructor hoặc để một phần tử null, constructor từ chối với `IllegalArgumentException` trước khi phương thức khác dùng dữ liệu.

Nhờ phân biệt **biến tham chiếu**, **đối tượng** và **mảng tham chiếu**, ta tránh hiểu nhầm rằng truyền đối tượng vào constructor sẽ tạo bản sao sâu của toàn bộ dữ liệu.

## 9. Những bước refactor an toàn và lỗi thường gặp

Khi chuyển từ một `main` dài sang nhiều lớp, có thể đi theo trình tự:

1. **Giữ hành vi đầu ra làm mốc.** Biên dịch/chạy bản ban đầu và lưu những trường hợp cần kiểm tra, gồm cả dữ liệu không hợp lệ nếu có.
2. **Nhóm dữ liệu luôn đi cùng nhau.** Ở đây `name` và `score` thuộc cùng một học viên, nên được giữ trong `Student` thay vì hai mảng song song.
3. **Đưa hành vi gắn với dữ liệu vào lớp đó.** Việc đổi và kiểm tra điểm thuộc `Student.improve`; việc tính trung bình thuộc `Classroom.average`.
4. **Giữ `main` làm nơi khởi tạo và điều phối.** Tạo `new Student(...)` rồi truyền cho `Classroom`; gọi các phương thức có trách nhiệm rõ ràng.
5. **Biên dịch tất cả lớp liên quan và so sánh kết quả.** Phiên bản mới phải cho kết quả nghiệp vụ tương đương và không thay đổi ngoài ý muốn.
6. **Chỉ tách thêm khi có lý do.** Không bắt buộc mỗi phương thức, biến hay phép tính nhỏ phải có một lớp riêng.

| Sai sót | Cách hiểu / cách sửa |
| --- | --- |
| Đặt tất cả các trường thành `public` để `main` tự sửa | Ưu tiên trường `private` và API có hợp đồng rõ |
| Cố gọi `Student.improve(1)` | `improve` là instance method; gọi qua đối tượng như `lan.improve(1)` |
| Viết `new Student(...)` nhưng gọi `new Classroom()` khi không có constructor không tham số | Phải dùng đúng constructor đã khai báo |
| Có hai lớp top-level `public` trong cùng một file `.java` | Tách thành file đúng tên lớp, hoặc dùng cách tổ chức hợp lệ khác |
| Chỉ biên dịch `SchoolApp.java` khi mã nguồn phụ thuộc chưa được tìm thấy | Chỉ rõ đủ file nguồn hoặc cấu hình sourcepath/classpath phù hợp |
| `java Student` dù `Student` không có `main` | Chạy `java SchoolApp` là lớp chứa điểm vào |
| Giả định `clone()` trên `Student[]` sao chép luôn từng `Student` | `clone()` chỉ sao chép mảng, các tham chiếu phần tử vẫn chung |
| Một lớp có cả giao diện, dữ liệu, lưu file và mọi phép tính | Xem xét tách trách nhiệm, nhưng không chia nhỏ một cách máy móc |
| Kết quả khác phiên bản `main` ban đầu | So lại dữ liệu đầu vào, thứ tự thay đổi trạng thái và phép tính |

### Bài tập

**Bài 1.** Thêm một học viên `Student("Hoa", 10)` vào đầu vào của `Classroom`, dự đoán điểm trung bình và kiểm tra bằng chạy chương trình.

**Bài 2.** Gọi `lan.improve(3)` khi Lan đang đạt 8. Vì sao bị từ chối? Phân tích trách nhiệm kiểm tra thuộc lớp nào.

**Bài 3.** Viết phương thức `isPassing()` trong `Student` với điều kiện điểm từ 5 trở lên. Có cần thay `SchoolApp` để biết cách so sánh điểm không?

**Bài 4.** Thêm `highestScore()` vào `Classroom`. Giải thích vì sao phép tính toàn lớp thuộc `Classroom` chứ không thuộc riêng từng `Student`.

**Bài 5.** Tạo `Student[] input = {lan, minh}`; đưa nó vào `Classroom`, rồi gán `input[0] = new Student("Hoa", 10)`. Vì sao danh sách trong lớp học không thay theo thao tác này, trong khi `lan.improve(1)` vẫn có thể được lớp học quan sát?

### Ghi nhớ

**`main` là điểm bắt đầu, không cần chứa toàn bộ logic của chương trình.** Bắt đầu bằng một `main` đơn giản là hợp lý; khi dữ liệu và hành vi phát triển, hãy tách thành các lớp có trách nhiệm rõ ràng, giữ trạng thái sau trường `private`, tạo đối tượng bằng `new` và gọi instance method qua biến tham chiếu. Các lớp có thể nằm ở file `.java` khác nhau, được biên dịch cùng nhau; khi chạy hãy chỉ rõ lớp có `main`. Mục tiêu tách lớp là **bảo toàn hành vi, giảm phụ thuộc và giúp mã dễ mở rộng/kiểm tra**, không phải tăng số lượng lớp cho đẹp.
