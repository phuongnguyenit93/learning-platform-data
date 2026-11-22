# Lớp và đối tượng trong Java: khái niệm, mục đích và mối liên hệ

Trong Java, **lớp (class)** mô tả một kiểu dữ liệu do lập trình viên định nghĩa; **đối tượng (object)** là một thực thể được tạo và sử dụng khi chương trình chạy. Nắm rõ hai khái niệm này giúp tổ chức dữ liệu cùng hành vi liên quan, mô hình hóa bài toán và hiểu cách các biến tham chiếu tương tác với đối tượng.

## 1. Lớp là gì?

Một lớp là **bản định nghĩa** cho các đối tượng cùng loại. Tùy mục đích, lớp có thể khai báo:

- **Thuộc tính/trường (field):** dữ liệu mô tả trạng thái của một đối tượng, ví dụ tên học viên và số tín chỉ.
- **Phương thức (method):** hành vi mà đối tượng có thể thực hiện, ví dụ cộng thêm tín chỉ hoặc hiển thị thông tin.
- **Constructor (hàm tạo):** đoạn mã khởi tạo trạng thái khi tạo một đối tượng mới; tên trùng tên lớp và không có kiểu trả về.
- **Quy tắc truy cập:** chẳng hạn `private` bảo vệ dữ liệu bên trong, còn phương thức phù hợp cung cấp cách sử dụng dữ liệu đó.

Khai báo một lớp **chưa đồng nghĩa** với việc đã có một đối tượng của lớp ấy. Ví dụ, dòng `class Student { ... }` mô tả kiểu `Student`, còn `new Student(...)` mới yêu cầu tạo một thực thể (với một lớp có thể khởi tạo được).

Hình dung lớp như bản thiết kế căn nhà: bản thiết kế cho biết các đặc điểm và cách tổ chức chung, còn từng căn nhà xây theo bản thiết kế là một thực thể riêng. Đây là phép so sánh để dễ học; trong Java, lớp còn chứa phương thức `static`, quy tắc truy cập và nhiều cấu trúc khác.

## 2. Đối tượng là gì?

Đối tượng là một **instance** (thể hiện) của một lớp tại thời điểm chạy. Có thể quan sát đối tượng qua ba khía cạnh:

1. **Trạng thái (state):** giá trị các trường thuộc về từng đối tượng, như `name = "An"`, `credits = 12`.
2. **Hành vi (behavior):** những thao tác có thể gọi trên đối tượng, như `earnCredits(3)` hoặc `summary()`.
3. **Danh tính (identity):** hai đối tượng có thể chứa dữ liệu giống nhau mà vẫn là hai đối tượng riêng. Trong Java, toán tử `==` trên hai tham chiếu kiểm tra chúng có trỏ đến cùng một đối tượng hay không.

Khi dùng `new` với một lớp thông thường, Java cấp phát đối tượng, thực hiện khởi tạo trường và gọi constructor phù hợp. Biểu thức tạo đối tượng cho ra **tham chiếu** đến thực thể mới, có thể lưu trong biến. Tham chiếu không nên hiểu là địa chỉ bộ nhớ số học để lập trình viên tự quản lý.

| Tiêu chí | Lớp (`class`) | Đối tượng (`object`) |
| --- | --- | --- |
| Vai trò | Định nghĩa kiểu, cấu trúc và hành vi | Thực thể cụ thể của kiểu đó khi chạy |
| Ví dụ | `Student` | Học viên An, học viên Bình |
| Dữ liệu trạng thái | Khai báo các trường instance | Giữ giá trị trường riêng của từng đối tượng |
| Hành vi | Khai báo/cài đặt phương thức | Thực hiện phương thức khi được gọi qua tham chiếu |
| Số lượng | Một định nghĩa có thể làm kiểu cho nhiều thực thể | Có thể tạo nhiều đối tượng từ cùng lớp |

Lớp là khái niệm về **kiểu và cách tổ chức**, còn đối tượng là khái niệm về **thực thể và trạng thái cụ thể**. Một lớp cũng có thể tồn tại mà chương trình không bao giờ khởi tạo đối tượng nào từ lớp ấy.

## 3. Ví dụ đầy đủ: một lớp, nhiều đối tượng

Tạo tệp **`ClassObjectDemo.java`** với nội dung sau. Tệp chứa hai lớp cấp cao nhất trong cùng tệp; chỉ `ClassObjectDemo` là `public`, nên tên tệp phải trùng với lớp `public`.

~~~java
class Student {
    private final String name;
    private int credits;

    Student(String name, int credits) {
        this.name = name;
        this.credits = credits;
    }

    void earnCredits(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        credits += amount;
    }

    String summary() {
        return name + ": " + credits + " tín chỉ";
    }
}

public class ClassObjectDemo {
    public static void main(String[] args) {
        Student an = new Student("An", 12);
        Student binh = new Student("Bình", 9);

        System.out.println(an.summary());

        an.earnCredits(3);

        System.out.println(an.summary());
        System.out.println(binh.summary());
    }
}
~~~

Biên dịch và chạy trên Java 17 trở lên (đứng tại thư mục chứa tệp):

~~~bash
javac -encoding UTF-8 ClassObjectDemo.java
java ClassObjectDemo
~~~

Kết quả chuẩn trên stdout:

~~~text
An: 12 tín chỉ
An: 15 tín chỉ
Bình: 9 tín chỉ
~~~

Phân tích từng phần:

- `Student` là **lớp**. Nó định nghĩa rằng một học viên có `name`, `credits` và các hành vi `earnCredits`, `summary`.
- `Student an` khai báo biến cục bộ tên `an` có **kiểu tham chiếu** `Student`; chỉ khai báo biến chưa tạo đối tượng.
- `new Student("An", 12)` tạo đối tượng thứ nhất và khởi tạo hai trường. `new Student("Bình", 9)` tạo đối tượng thứ hai.
- `an` và `binh` giữ hai tham chiếu đến hai đối tượng khác nhau. Chúng cùng tuân theo định nghĩa lớp `Student` nhưng có **trạng thái độc lập**.
- `this.name = name` lấy đối tượng đang được khởi tạo ở phía trái và tham số `name` ở phía phải. `this` là tham chiếu tới đối tượng hiện tại trong constructor hoặc phương thức instance.
- `an.earnCredits(3)` chỉ cập nhật trường `credits` của đối tượng mà `an` tham chiếu. Giá trị `credits` của `binh` vẫn là 9.
- `private` ngăn mã bên ngoài lớp sửa trực tiếp các trường. Thay đổi trạng thái thông qua `earnCredits` cho phép kiểm tra `amount > 0`.
- `final` ở trường `name` ngăn việc gán lại trường đó sau khi đã được khởi tạo hợp lệ; nó không tự làm cho cả đối tượng trở thành bất biến. `credits` vẫn có thể thay đổi.

Quan hệ giữa lớp, biến tham chiếu và đối tượng có thể hình dung như sau:

~~~text
        Định nghĩa lớp Student
        (fields, constructor, methods)
                  |
           mô tả kiểu của
                  |
            +-----+-----+
            |           |
          an            binh        <- biến tham chiếu
            |           |
            v           v
     Student object  Student object  <- hai instance riêng
     name = "An"     name = "Bình"
     credits = 15    credits = 9
~~~

**Điểm cốt lõi:** định nghĩa trường và phương thức nằm trong lớp, còn giá trị của các trường instance gắn với từng đối tượng. Việc gọi phương thức instance thường tác động lên đối tượng nhận lời gọi.

## 4. Biến tham chiếu không phải là chính đối tượng

Lỗi tư duy phổ biến là coi `Student an` hoặc `Box first` chính là đối tượng. Thực tế, biến kiểu tham chiếu **lưu tham chiếu** đến một đối tượng hoặc giá trị `null`. Vì vậy, nhiều biến có thể cùng tham chiếu một đối tượng; việc tạo biến mới không tự tạo instance mới.

Tạo tệp độc lập **`ReferenceDemo.java`**:

~~~java
class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

public class ReferenceDemo {
    public static void main(String[] args) {
        Box first = new Box(5);
        Box alias = first;
        Box separate = new Box(5);

        alias.value = 7;

        System.out.println(first.value);
        System.out.println(separate.value);
        System.out.println(first == alias);
        System.out.println(first == separate);

        first = null;
        System.out.println(alias.value);
    }
}
~~~

~~~bash
javac ReferenceDemo.java
java ReferenceDemo
~~~

Stdout:

~~~text
7
5
true
false
7
~~~

Tại sao?

1. `first` trỏ tới đối tượng `Box` có `value = 5`.
2. `alias = first` **sao chép tham chiếu**, không sao chép đối tượng. Hai biến cùng trỏ đến một `Box`.
3. `separate = new Box(5)` tạo một `Box` khác, dù ban đầu có cùng giá trị 5.
4. `alias.value = 7` thay đổi đối tượng chung, nên `first.value` cũng là 7; `separate.value` vẫn là 5.
5. `first == alias` là `true`, còn `first == separate` là `false`: `==` ở đây so sánh **danh tính tham chiếu**, không so sánh nội dung các trường.
6. `first = null` chỉ thay đổi giá trị biến `first`; đối tượng cũ vẫn truy cập được qua `alias`.

Hình dung:

~~~text
first ------+
            |
alias ------+----> Box { value = 7 }

separate --------> Box { value = 5 }
~~~

Khi `first = null`, chỉ mũi tên của `first` biến mất. `alias` vẫn còn tham chiếu tới đối tượng. Nếu một đối tượng không còn đường tham chiếu có thể sử dụng đến nó, nó **có thể đủ điều kiện** để garbage collector thu hồi về sau; việc gán `null` không có nghĩa là thu hồi ngay.

Java truyền đối số **theo giá trị**: khi đưa biến tham chiếu vào phương thức, giá trị được sao chép chính là tham chiếu. Bởi vậy, phương thức có thể thay đổi trạng thái đối tượng chung nếu được phép, nhưng gán lại biến tham số không làm biến của bên gọi trỏ tới đối tượng khác. Đây là hệ quả trực tiếp của cách tham chiếu hoạt động, không phải cơ chế truyền tham chiếu kiểu C++.

## 5. Vì sao cần lớp và đối tượng?

Lớp và đối tượng giúp giải quyết các vấn đề mà một tập hợp biến rời rạc khó xử lý:

- **Gom dữ liệu với hành vi:** thay vì tách `studentName`, `studentCredits` và mọi hàm xử lý ở nhiều nơi, `Student` cung cấp một nơi định nghĩa các thao tác liên quan.
- **Tái sử dụng khuôn mẫu:** viết lớp một lần, tạo nhiều đối tượng cho nhiều học viên, mỗi đối tượng tự giữ trạng thái.
- **Mô hình hóa bài toán:** các khái niệm như đơn hàng, tài khoản hoặc phiên học có thể trở thành lớp; từng trường hợp cụ thể là một object.
- **Đóng gói, bảo vệ quy tắc:** giữ trường `private`, cung cấp phương thức để kiểm tra điều kiện trước khi thay đổi dữ liệu.
- **Dễ thay đổi và kiểm thử:** mã gọi làm việc qua các thao tác có ý nghĩa; lớp có trách nhiệm rõ ràng sẽ dễ bảo trì hơn.

Không phải danh từ nào trong yêu cầu cũng phải biến thành lớp. Chỉ tạo lớp khi nó thật sự đại diện cho dữ liệu/hành vi hoặc quy tắc cần quản lý. Tránh lớp chỉ chứa hàng loạt trường `public` khiến các thành phần khác phải trực tiếp sửa trạng thái mà không qua kiểm tra.

## 6. Thành viên instance và thành viên static

Cùng một lớp có hai nhóm thành viên cần phân biệt:

| Loại | Thuộc về | Cách dùng thông thường |
| --- | --- | --- |
| Trường instance, như `credits` | Mỗi đối tượng riêng | `an.summary()`, truy cập trường từ phương thức của đối tượng |
| Phương thức instance, như `earnCredits` | Hành vi gọi với một đối tượng nhận | `an.earnCredits(3)` |
| Trường `static` | Lớp, dùng chung cho các đối tượng của lớp trong cùng ngữ cảnh runtime | `Student.createdCount` |
| Phương thức `static` | Lớp, không có đối tượng nhận `this` | `Math.max(2, 5)` |

Ví dụ minh họa thành viên lớp (đoạn này là **một phần lớp**, không phải chương trình độc lập):

~~~java
class Counter {
    static int created = 0;

    Counter() {
        created++;
    }
}
~~~

Sau khi tuần tự gọi `new Counter()` hai lần, `Counter.created` bằng 2; số đếm **dùng chung**, không có một bản riêng cho mỗi đối tượng. Với ứng dụng đa luồng, phép `created++` chưa tự bảo đảm an toàn đồng thời; đó là vấn đề khác, không phải đặc tính mặc định của `static`.

Một phương thức `static` không có `this` để truy cập trực tiếp trạng thái instance. Tuy nhiên, nó vẫn có thể nhận tham chiếu đối tượng qua tham số rồi thao tác trên đối tượng đó.

## 7. Từ yêu cầu thực tế đến lớp và đối tượng

Giả sử cần quản lý kết quả học tập. Một cách suy nghĩ hữu ích là:

1. **Xác định thực thể cần quản lý:** mỗi học viên có dữ liệu và các thao tác riêng, nên có thể dùng lớp `Student`.
2. **Chọn trạng thái:** tên và số tín chỉ là ví dụ tối giản; chỉ thêm trường thật sự cần cho hành vi.
3. **Chọn hành vi:** cộng tín chỉ, lấy thông tin tóm tắt; hành vi nên có tên thể hiện ý nghĩa nghiệp vụ.
4. **Chọn quy tắc hợp lệ:** số tín chỉ cộng thêm phải dương; phương thức đổi trạng thái nên chịu trách nhiệm kiểm tra.
5. **Tạo các instance cần thiết:** `an` và `binh` đại diện cho hai học viên khác nhau. Sự thay đổi của người này không tự làm thay đổi người kia.
6. **Kiểm tra danh tính và chia sẻ tham chiếu:** nếu hai biến cần quản lý đúng cùng một học viên, có thể truyền cùng tham chiếu; nếu cần hai thực thể độc lập, phải tạo hai đối tượng phù hợp.

Một lớp không nhất thiết tương ứng đúng một đối tượng. Mối quan hệ phổ biến là **một định nghĩa lớp → không, một hoặc nhiều instance**; nhiều biến tham chiếu có thể cùng trỏ đến **một instance**.

## 8. Vòng đời cơ bản và giới hạn cần hiểu đúng

- **Khi viết/biên dịch:** khai báo `class` xác lập kiểu cho compiler kiểm tra cú pháp, quyền truy cập và kiểu dữ liệu. Lớp có thể được JVM nạp/khởi tạo khi cần trong lúc chạy.
- **Khi tạo đối tượng:** biểu thức `new Student(...)` yêu cầu tạo instance và chạy constructor. Với lớp trừu tượng (`abstract class`) hay interface, không thể `new` trực tiếp chính kiểu trừu tượng ấy.
- **Khi sử dụng:** biến giữ tham chiếu; truy cập thành viên instance thông qua tham chiếu hợp lệ. Gọi phương thức trên tham chiếu `null` gây `NullPointerException` trong trường hợp thông thường.
- **Khi không còn truy cập được:** đối tượng có thể được garbage collector thu hồi vào thời điểm JVM quyết định. Không lập trình dựa trên giả định rằng việc bỏ tham chiếu sẽ hủy đối tượng tức thì.

Không phải mọi đối tượng Java đều được viết dưới dạng `new T(...)`: ví dụ literal `"hello"` biểu diễn một `String` theo cơ chế riêng của ngôn ngữ. Nhưng cả `String` và `Student` đều là kiểu tham chiếu (khác với primitive `int`, `boolean`, `double`).

Phân biệt thêm: trường instance kiểu tham chiếu chưa gán trong quá trình khởi tạo mặc định có giá trị `null`; biến **cục bộ** trong phương thức không được tự động coi là đã khởi tạo để đọc. Compiler yêu cầu biến cục bộ phải được gán chắc chắn trước khi sử dụng.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Viết `class Student` là đã tạo ra học viên” | Khai báo lớp định nghĩa kiểu; tạo instance là thao tác khác. |
| “`Student x;` đã có object” | Đó chỉ là khai báo một biến; chưa có đối tượng nào được tạo bởi câu lệnh ấy. |
| “Hai biến tham chiếu luôn là hai object” | Hai biến có thể cùng trỏ một đối tượng sau phép gán `alias = first`. |
| “Hai object có cùng trường thì `==` là `true`” | `==` với tham chiếu kiểm tra cùng đối tượng; so sánh giá trị logic cần quy tắc `equals` phù hợp. |
| “`static` có một bản sao ở mỗi object” | Trường `static` thuộc lớp và được chia sẻ theo ngữ cảnh nạp lớp. |
| “Gán `null` sẽ hủy object ngay” | Chỉ bỏ một tham chiếu; thu gom bộ nhớ do JVM quyết định. |
| “Trường `final` biến mọi trạng thái thành bất biến” | `final` ngăn gán lại chính trường; những trường khác vẫn có thể thay đổi. |

Đừng nhầm giữa **giống dữ liệu** và **cùng danh tính đối tượng**. Đây là nền tảng trước khi học sâu về `equals()`, `hashCode()`, sao chép đối tượng, đóng gói, kế thừa và đa hình.

## 10. Tự kiểm tra kiến thức

1. Khi có `Student a = new Student("An", 12);`, phần nào là tên lớp, phần nào là biến tham chiếu, phần nào thực hiện tạo đối tượng?
2. Vì sao sau khi gọi `a.earnCredits(3)`, một đối tượng `Student` khác vẫn giữ số tín chỉ ban đầu?
3. Nếu `Student b = a;`, gọi `b.earnCredits(2)` có làm thay đổi kết quả `a.summary()` không? Giải thích.
4. Nếu tạo `Student c = new Student("An", 12);`, điều kiện `a == c` nói lên điều gì? Việc hai người cùng tên có ảnh hưởng kết quả so sánh danh tính không?
5. Khi nào nên khai báo một thành viên `static` thay vì instance?

**Đối chiếu:** (1) `Student` là lớp, `a` là biến, `new Student(...)` tạo object; (2) hai instance giữ trường `credits` riêng; (3) có, vì `b` và `a` cùng tham chiếu một object; (4) kiểm tra cùng instance, không dựa vào tên, và `new` lần nữa tạo instance khác; (5) khi dữ liệu/hành vi thuộc cấp lớp, không phụ thuộc trạng thái riêng của một đối tượng.

Hiểu vững mối quan hệ **lớp định nghĩa kiểu — đối tượng mang trạng thái — biến tham chiếu chỉ tới đối tượng** sẽ giúp đọc và viết chương trình Java hướng đối tượng một cách chính xác.
