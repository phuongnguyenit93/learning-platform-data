# Lớp mô tả kiểu và đối tượng là thể hiện cụ thể — Java 17+

## 1. Lớp khác đối tượng như thế nào?

Trong Java, **lớp (class)** định nghĩa một **kiểu dữ liệu**: tên kiểu, các thuộc tính (*fields*), hành vi (*methods*) và cách khởi tạo (*constructors*). **Đối tượng (object)** là một **thể hiện cụ thể (instance)** của kiểu đó, được tạo khi chương trình chạy.

~~~java
class Student {                          // Định nghĩa một lớp.
    String name;                         // Trường instance.
    int score;

    Student(String name, int score) {    // Constructor.
        this.name = name;
        this.score = score;
    }

    void printInfo() {                   // Phương thức instance.
        System.out.println(name + ":" + score);
    }
}
~~~

~~~java
Student an = new Student("An", 70);       // Một đối tượng.
Student binh = new Student("Binh", 85);   // Đối tượng thứ hai.
an.printInfo();
binh.printInfo();
~~~

**Exact expected stdout** (khi đặt hai câu gọi trong `main`):

~~~text
An:70
Binh:85
~~~

`Student` là **kiểu chung** mô tả các đặc điểm và thao tác; `an` và `binh` là **hai biến tham chiếu đến hai đối tượng Student khác nhau**. Chúng dùng cùng định nghĩa lớp nhưng có dữ liệu `name`, `score` riêng.

## 2. Phân biệt class, object, reference và constructor

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| Class | `class Student { ... }` | Khai báo kiểu và các thành viên |
| Object/instance | Đối tượng do `new Student(...)` tạo | Thể hiện có trạng thái riêng |
| Reference variable | `Student an` | Biến có kiểu `Student`, giữ giá trị tham chiếu tới object (hoặc `null`) |
| Constructor | `Student(String name, int score)` | Khởi tạo object khi được gọi qua `new` |
| Instance field | `name`, `score` | Dữ liệu thuộc từng instance |
| Instance method | `printInfo()` | Hành vi gọi trên một instance |
| Static member | `static int created` | Thành viên gắn với lớp, không tồn tại một bản riêng ở mỗi object |

Câu lệnh:

~~~java
Student student = new Student("Lan", 90);
~~~

có hai phía:

1. `Student student` khai báo **biến tham chiếu** tên `student`.
2. `new Student("Lan", 90)` tạo **đối tượng**, gọi constructor và cung cấp giá trị tham chiếu để lưu vào `student`.

Chỉ viết `Student student;` **không tạo object**, và vì là biến cục bộ chưa được gán, không được đọc nó trước khi gán. Nếu chủ động viết `Student student = null;`, biến đã được gán nhưng **chưa trỏ đến đối tượng nào**.

## 3. Mỗi đối tượng có trạng thái instance độc lập

~~~java
Student an = new Student("An", 70);
Student binh = new Student("Binh", 85);

an.score = 75; // Minh họa khi field có thể truy cập.
System.out.println(an.score);
System.out.println(binh.score);
~~~

**Exact expected stdout:**

~~~text
75
85
~~~

Thay đổi trường `score` của `an` không thay trường `score` của `binh`, vì hai object được tạo bằng **hai lần `new`**.

Một mô hình tham chiếu:

~~~text
Student an   ──────> Object #1: {name="An",   score=75}
Student binh ──────> Object #2: {name="Binh", score=85}

              Cùng kiểu Student, khác đối tượng và trạng thái.
~~~

Tên `Object #1` và `Object #2` chỉ là chú giải; không phải số nhận dạng Java tự in ra. Java không bảo đảm các object nằm ở vị trí bộ nhớ cụ thể mà chương trình được phép dựa vào.

Trong code thực tế, thường khai báo field `private` và cung cấp phương thức truy cập/cập nhật có kiểm tra, thay vì cho phép gán tùy ý vào `student.score`.

## 4. Hai biến có thể trỏ cùng một đối tượng

~~~java
Student an = new Student("An", 70);
Student alias = an;                 // Không gọi new, không tạo Student mới.
alias.score = 80;
System.out.println(an.score);
System.out.println(an == alias);
~~~

**Exact expected stdout:**

~~~text
80
true
~~~

`alias = an` **sao chép giá trị tham chiếu**. Vì `an` và `alias` đang chỉ đến cùng object, sửa trạng thái qua biến nào cũng thấy từ biến kia.

Nếu sau đó:

~~~java
alias = new Student("Chi", 90);
System.out.println(an == alias);
~~~

**Exact expected stdout (tiếp nối):**

~~~text
false
~~~

`alias` chuyển sang object mới; `an` vẫn giữ tham chiếu tới object cũ. **Gán lại biến tham chiếu** không tự thay một biến tham chiếu khác.

Với hai object được tạo riêng bằng `new`, toán tử `==` so sánh xem các tham chiếu có chỉ đến **cùng object** hay không. Nó không tự so sánh mọi field bên trong. Nếu cần kiểm tra giá trị nghiệp vụ tương đương, có thể thiết kế `equals`/`hashCode` phù hợp ở bài học nâng cao.


## 5. Constructor giúp đối tượng có trạng thái ban đầu

Khi gọi `new Student("Lan", 90)`, Java chọn constructor tương ứng để khởi tạo **chính instance mới**. Constructor mang tên lớp, không khai báo kiểu trả về và thường kiểm tra đầu vào trước khi hoàn tất. Ví dụ:

~~~java
class Student {
    private final String name;
    private int score;

    Student(String name, int score) {
        if (name == null || name.isBlank() || score < 0 || score > 100) {
            throw new IllegalArgumentException("invalid student");
        }
        this.name = name.strip();
        this.score = score;
    }
}
~~~

`this.name` là field của object đang tạo, còn `name` là tham số. `final` ngăn gán lại field `name` sau khởi tạo, không khiến toàn bộ object bất biến. Nếu constructor ném ngoại lệ, biểu thức `new` không trả tham chiếu cho caller. Các quy tắc về constructor mặc định, overload, `this(...)` và `super(...)` được thực hành ở bài **Hàm khởi tạo thiết lập giá trị ban đầu**.

## 6. Đối tượng có hành vi riêng, lớp có thành viên chung

~~~java
// Với instance method:
an.increase(5); // Thay trạng thái của đối tượng an.

// Với static method do lớp định nghĩa:
Student.getCreatedCount(); // Đọc bộ đếm gắn với lớp Student.
~~~

Phương thức **instance** chạy với một đối tượng nhận lời gọi; trong thân nó có thể dùng `this` để chỉ object ấy. Thành viên **static** gắn với lớp, không có một bản riêng trên từng object và static method không có `this`. Ví dụ hoàn chỉnh bên dưới minh họa cả hai, trong khi bài **Phân biệt thành viên static với thành viên đối tượng** giải thích phạm vi và rủi ro của trạng thái chung.

## 7. Chương trình Java 17+ hoàn chỉnh

Lưu đúng file **`ClassObjectBasicsDemo.java`**:

~~~java
public final class ClassObjectBasicsDemo {
    private ClassObjectBasicsDemo() {}

    // Lớp mô tả kiểu đối tượng Student.
    static final class Student {
        private static int createdCount;

        private final String name;
        private int score;

        Student(String name, int score) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name is blank");
            }
            if (score < 0 || score > 100) {
                throw new IllegalArgumentException("score out of range");
            }
            this.name = name.strip();
            this.score = score;
            createdCount++;
        }

        String getName() {
            return name;
        }

        int getScore() {
            return score;
        }

        void increase(int points) {
            if (points < 0 || points > 100 - score) {
                throw new IllegalArgumentException("invalid increase");
            }
            score += points;
        }

        String describe() {
            return name + ":" + score;
        }

        static int getCreatedCount() {
            return createdCount;
        }
    }

    public static void main(String[] args) {
        System.out.println("created initially=" + Student.getCreatedCount());

        Student an = new Student(" An ", 70);
        Student binh = new Student("Binh", 85);
        System.out.println("created after two=" + Student.getCreatedCount());

        System.out.println("an=" + an.describe());
        System.out.println("binh=" + binh.describe());
        System.out.println("an name=" + an.getName());

        an.increase(5);
        System.out.println("an after increase=" + an.getScore());
        System.out.println("binh unchanged=" + binh.getScore());
        System.out.println("two objects same=" + (an == binh));

        Student alias = an;
        alias.increase(5);
        System.out.println("alias same=" + (an == alias));
        System.out.println("an via alias=" + an.describe());
        System.out.println("created after alias=" + Student.getCreatedCount());

        alias = new Student("Chi", 90);
        System.out.println("alias replaced same=" + (an == alias));
        System.out.println("an still=" + an.describe());
        System.out.println("alias now=" + alias.describe());
        System.out.println("created after third=" + Student.getCreatedCount());

        Student missing = null;
        System.out.println("missing null=" + (missing == null));

        try {
            new Student("", 10);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid name=" + ex.getMessage());
        }
        try {
            an.increase(30);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid increase=" + ex.getMessage());
        }
        System.out.println("created at end=" + Student.getCreatedCount());
    }
}
~~~

**Yêu cầu:** JDK 17 trở lên; mở terminal tại thư mục chứa file. Không cần Maven, Gradle, thư viện ngoài hay preview features.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 ClassObjectBasicsDemo.java
java -cp . ClassObjectBasicsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\ClassObjectBasicsDemo.java
java -cp . ClassObjectBasicsDemo
~~~

### Exact expected stdout

~~~text
created initially=0
created after two=2
an=An:70
binh=Binh:85
an name=An
an after increase=75
binh unchanged=85
two objects same=false
alias same=true
an via alias=An:80
created after alias=2
alias replaced same=false
an still=An:80
alias now=Chi:90
created after third=3
missing null=true
invalid name=name is blank
invalid increase=invalid increase
created at end=3
~~~

**Lưu ý tràn số:** Vì `score` luôn nằm trong `0..100`, so sánh `points > 100 - score` sẽ từ chối cả đối số rất lớn như `Integer.MAX_VALUE`; kiểm tra `score + points > 100` có thể sai do phép cộng `int` tràn trước khi so sánh.

**Đối chiếu:** hai lần `new` đầu tạo hai object nên `createdCount == 2`. `alias = an` không tạo object; gọi `alias.increase(5)` thay đúng object `an` đang chỉ đến. Sau `alias = new Student("Chi", 90)`, có object thứ ba, còn `an` giữ nguyên trạng thái 80. Constructor từ chối tên rỗng, nên lần tạo thất bại không tăng bộ đếm trong mã này.

## 8. Những lỗi thường gặp

| Sai lầm | Vì sao sai? | Cách hiểu đúng |
|---|---|---|
| Nghĩ `class Student` tự tạo học viên cụ thể | Chỉ định nghĩa kiểu | Cần `new Student(...)` để tạo instance |
| Nghĩ `Student s;` tạo object | Chỉ khai báo biến tham chiếu local | Gán tham chiếu object trước khi dùng |
| Nghĩ `Student s = null;` là object rỗng | `null` là không trỏ đến object | Không gọi `s.method()` khi null |
| Nghĩ `Student b = a;` tạo bản sao | Chỉ sao chép tham chiếu | `a` và `b` cùng object |
| Nghĩ thay `alias` sang `new` làm `an` đổi theo | Hai biến tham chiếu được gán độc lập | Gán lại alias không gán lại an |
| Nghĩ các object chia sẻ toàn bộ instance fields | Instance có trạng thái riêng | Chỉ thành viên static chung theo lớp |
| Viết constructor `void Student(...)` | Đó là method, không phải constructor | Constructor không có kiểu trả về |
| Truy cập `private` field từ bên ngoài lớp | Vi phạm truy cập | Dùng phương thức phù hợp |
| Dùng `==` để so nội dung tất cả fields | `==` với object reference so identity | Dùng chính sách equals khi cần |
| In object trực tiếp rồi mong format ổn định | `toString` mặc định không mô tả giá trị nghiệp vụ | Viết `describe`/`toString` tùy nhu cầu |

## 9. Bài tập có đáp án

**A — Tạo bao nhiêu object?**

~~~java
Student first = new Student("Lan", 50);
Student second = first;
Student third = new Student("Mai", 60);
~~~

**Đáp án:** **2 Student objects** do có hai lần `new Student`. `second` chỉ là alias của `first`.

**B — Sau phép cập nhật qua alias thì sao?**

~~~java
Student first = new Student("Lan", 50);
Student alias = first;
alias.increase(10);
System.out.println(first.getScore());
~~~

**Đáp án:** `60`, vì hai biến trỏ tới cùng object.

**C — Hai object cùng dữ liệu có chắc `==` true không?**

~~~java
Student a = new Student("An", 70);
Student b = new Student("An", 70);
System.out.println(a == b);
~~~

**Đáp án:** `false`. Hai lần `new` tạo hai object riêng, dù field có giá trị giống nhau.

**D — Khi nào dùng `static`?** Khi dữ liệu/hành vi gắn với **lớp**, chẳng hạn bộ đếm số object tạo thành công trong ví dụ. Với dữ liệu của từng học viên, dùng instance field.

**E — Field nào thuộc từng object?** Trong `Student` của chương trình, `name` và `score` là instance fields; `createdCount` là static field.

## 10. Checklist và kết luận

- [ ] Hiểu **class định nghĩa kiểu**, object là instance cụ thể.
- [ ] Phân biệt khai báo biến tham chiếu với tạo object bằng `new`.
- [ ] Biết constructor thiết lập trạng thái ban đầu.
- [ ] Nhận ra mỗi object có bộ instance fields riêng.
- [ ] Hiểu `b = a` chia sẻ object, không tự sao chép.
- [ ] Biết `==` so identity của tham chiếu object.
- [ ] Phân biệt instance method và static member.
- [ ] Nhận diện `null` và tránh dereference khi không có object.
- [ ] Biết dùng `private` và method để quản lý trạng thái.
- [ ] Biên dịch và chạy `ClassObjectBasicsDemo.java` với JDK 17+, đối chiếu exact stdout.

**Kết luận:** **Lớp là định nghĩa kiểu và hành vi; đối tượng là một thể hiện cụ thể được tạo khi chạy**. Nhiều object có thể cùng kiểu nhưng giữ trạng thái riêng; nhiều biến tham chiếu cũng có thể cùng trỏ đến **một** object. Đó là nền tảng để hiểu constructor, instance fields, instance methods và `static` trong Java.