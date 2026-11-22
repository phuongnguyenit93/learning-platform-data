# Trường biểu diễn dữ liệu và phương thức biểu diễn hành vi — Java 17+

## 1. Hai thành phần cơ bản của một lớp

Trong Java, **lớp (class)** mô tả kiểu đối tượng. Một lớp thường tập hợp:

- **Trường (field)** để lưu **dữ liệu/trạng thái** của đối tượng, chẳng hạn tên sách và tình trạng đang được mượn.
- **Phương thức (method)** để mô tả **hành vi/thao tác**, chẳng hạn mượn sách, trả sách hoặc hiển thị tình trạng.

~~~java
class Book {
    String title;       // Field: dữ liệu về cuốn sách.
    boolean borrowed;   // Field: trạng thái hiện tại.

    void borrow() {     // Method: một hành vi.
        borrowed = true;
    }

    void giveBack() {   // Method: một hành vi khác.
        borrowed = false;
    }
}
~~~

Ví dụ này chỉ giới thiệu cấu trúc. Code hoàn chỉnh bên dưới sẽ dùng `private` và kiểm tra điều kiện để ngăn mượn một cuốn sách đang được mượn.

**Phân biệt quan trọng:** một trường mô tả “đối tượng **đang có gì/ở trạng thái nào**”; một phương thức mô tả “đối tượng **có thể làm gì**”. Hai thành phần không tách rời: hành vi có thể **đọc hoặc cập nhật** trạng thái nhưng cần tuân thủ quy tắc của lớp.

## 2. Khai báo và truy cập field

Cú pháp khái quát:

~~~java
[accessModifier] [static] [final] Type fieldName;
~~~

Ví dụ:

~~~java
class Student {
    private String name;
    private int score;
    private boolean active;
}
~~~

`name`, `score`, `active` là ba **instance fields** — mỗi đối tượng `Student` có phần trạng thái riêng. Khi tạo hai đối tượng bằng hai lần `new`, thay đổi field của đối tượng thứ nhất không tự làm thay đổi đối tượng thứ hai.

Với field không được khởi tạo tường minh, Java thiết lập **giá trị mặc định** khi đối tượng được tạo:

| Kiểu field | Giá trị mặc định |
|---|---|
| `int`, `long`, các kiểu số nguyên | `0` tương ứng |
| `double`, `float` | `0.0` tương ứng |
| `boolean` | `false` |
| `char` | `'\\u0000'` |
| Kiểu tham chiếu như `String`, `int[]` | `null` |

**Khác biệt:** biến cục bộ khai báo `int n;` **không có giá trị mặc định để đọc ngay**. Với field, Java khởi tạo mặc định trước khi constructor hoàn tất.

Trong code dùng `private`, mã bên ngoài lớp **không được viết trực tiếp** `book.borrowed = true;`. Lớp nên công khai một hành vi hợp lệ như `book.borrow()` nếu việc chuyển trạng thái cần quy tắc kiểm tra.

## 3. Khai báo method và gọi hành vi

Cú pháp khái quát của một phương thức:

~~~java
[accessModifier] [static] ReturnType methodName(ParameterList) {
    // Thân phương thức.
}
~~~

Ví dụ:

~~~java
class Counter {
    private int value;

    void increase() {
        value++;
    }

    void add(int amount) {
        value += amount;
    }

    int getValue() {
        return value;
    }
}
~~~

- `void increase()`: hành vi không nhận đối số, không trả một giá trị.
- `void add(int amount)`: nhận **đối số** khi gọi (ví dụ `add(3)`) qua tham số `amount`.
- `int getValue()`: trả về `int` bằng lệnh `return value;`.
- `getValue()` **đọc** trạng thái; `increase()`, `add(...)` **thay đổi** trạng thái.

~~~java
Counter counter = new Counter();
counter.increase();
counter.add(3);
System.out.println(counter.getValue());
~~~

**Exact expected stdout:**

~~~text
4
~~~

Ví dụ trên sử dụng lớp `Counter` ngay phía trên; không phải chương trình độc lập nếu chỉ sao chép riêng bốn dòng gọi. Chương trình hoàn chỉnh để chạy bằng CLI được cung cấp ở mục 9.


## 4. Constructor cung cấp trạng thái bắt đầu cho field

~~~java
class Student {
    private final String name;
    private int score;

    Student(String name, int score) {
        if (score < 0 || score > 100) {
            throw new IllegalArgumentException("score out of range");
        }
        this.name = name;
        this.score = score;
    }
}
~~~

Constructor kiểm tra và gán field của instance mới. Một field `final` không được gán lại sau khi hoàn tất khởi tạo theo quy tắc Java; field khác vẫn có thể đổi qua hành vi có kiểm tra. Từ khóa `this` chọn **field của object hiện tại** khi tên field trùng tham số. Ở bài này, quan trọng là **dữ liệu ban đầu và các method cập nhật sau đó tuân thủ cùng hợp đồng trạng thái**. Các biến thể constructor và `this(...)` có bài riêng.

## 5. Method thao tác trên trạng thái của receiver

Nếu `student.addScore(5)` là một lời gọi instance, `addScore` sẽ đọc/cập nhật field của object mà `student` đang trỏ đến. Có thể viết `this.score += points;` hoặc `score += points;` khi tên không bị che khuất. Để phân biệt field với tham số cùng tên, viết rõ `this.score = score;`.

Hai object được tạo riêng có field instance riêng; hai biến cùng tham chiếu một object sẽ quan sát cùng trạng thái. Phần này giúp đọc hành vi `Book.borrow()` ở dưới, không yêu cầu học lại toàn bộ phép gán tham chiếu.

## 6. Tại sao nên để field `private`?

Ví dụ phản diện:

~~~java
class Book {
    public boolean borrowed;
}
~~~

Code khác có thể đặt `book.borrowed = true;` hoặc `false` từ bất kỳ đâu cho phép truy cập, ngay cả khi quy trình mượn/trả còn phải cập nhật thống kê hoặc kiểm tra điều kiện. Trạng thái dễ trở nên **không nhất quán**.

Đóng gói (*encapsulation*) giúp lớp tự quản lý dữ liệu:

~~~java
class Book {
    private boolean borrowed;
    private int borrowCount;

    boolean borrow() {
        if (borrowed) return false;
        borrowed = true;
        borrowCount++;
        return true;
    }

    boolean returnBook() {
        if (!borrowed) return false;
        borrowed = false;
        return true;
    }

    boolean isBorrowed() {
        return borrowed;
    }
}
~~~

Hợp đồng:

- `borrow()` trả `true` nếu mượn thành công và **chuyển trạng thái** sang đang mượn; trả `false` nếu đã được mượn, không tăng `borrowCount`.
- `returnBook()` trả `true` khi cuốn sách đang được mượn và được trả thành công; nếu đã có sẵn thì trả `false`.
- `isBorrowed()` chỉ **đọc trạng thái**, không sửa dữ liệu.

`private` không tự đảm bảo mọi thiết kế đều đúng; lợi ích là các thay đổi trạng thái có thể tập trung trong những phương thức kiểm soát quy tắc. Không nhất thiết phải tạo setter cho mọi field: một setter công khai không có kiểm tra có thể làm mất ý nghĩa đóng gói.


## 7. Field và method instance là trọng tâm của mô hình Book

Trong ví dụ `Book`, `borrowed` và `borrowCount` là **instance fields**: mỗi sách giữ tình trạng và số lượt mượn của mình. `borrow()`, `returnBook()`, `summary()` là **instance methods** đọc hoặc thay đổi những field ấy.

`createdCount` và `getCreatedCount()` là thành viên **static**, dùng chung ở cấp lớp để minh họa bộ đếm số đối tượng tạo thành công. Gọi `Book.getCreatedCount()` qua tên lớp. Static method không có `this` để truy cập trạng thái của một sách cụ thể; bài riêng về `static` sẽ giải thích sâu hơn thời điểm khởi tạo, chia sẻ trạng thái và đa luồng.

## 8. Dữ liệu, hành vi và tính nhất quán của đối tượng

Một mô hình đơn giản:

~~~text
                  class Book
         +--------------------------+
FIELDS   | title: String            |  Trạng thái
         | borrowed: boolean        |
         | borrowCount: int         |
         +--------------------------+
METHODS  | borrow(): boolean        |  Hành vi
         | returnBook(): boolean    |
         | summary(): String        |
         +--------------------------+

bookA ──> {title="Java", borrowed=true,  borrowCount=2}
bookB ──> {title="OOP",  borrowed=false, borrowCount=0}
~~~

Hai đối tượng cùng kiểu `Book` có thể ở **hai trạng thái khác nhau**. Các phương thức được khai báo trong một định nghĩa lớp và hoạt động trên đối tượng nhận lời gọi.

**Bất biến nghiệp vụ** (*invariant*) của ví dụ: `borrowCount` không âm; mỗi lần mượn thành công mới tăng bộ đếm; trả sách không làm giảm tổng số lượt đã mượn. Constructor kiểm tra `title` không rỗng để tránh tạo object thiếu tên hợp lệ.

Một getter thường **trả về** thông tin, còn một phương thức hành vi như `borrow()` truyền đạt rõ hơn mục đích nghiệp vụ so với cho phép bên ngoài sửa trực tiếp field `borrowed`.

## 9. Chương trình Java 17+ hoàn chỉnh

Lưu file đúng tên **`FieldsMethodsDemo.java`**:

~~~java
public final class FieldsMethodsDemo {
    private FieldsMethodsDemo() {}

    static final class Book {
        private static int createdCount;

        private final String title;
        private boolean borrowed;
        private int borrowCount;

        Book(String title) {
            if (title == null || title.isBlank()) {
                throw new IllegalArgumentException("title must not be blank");
            }
            this.title = title.strip();
            // borrowed mặc định false, borrowCount mặc định 0.
            createdCount++;
        }

        boolean borrow() {
            if (borrowed) {
                return false;
            }
            borrowed = true;
            borrowCount++;
            return true;
        }

        boolean returnBook() {
            if (!borrowed) {
                return false;
            }
            borrowed = false;
            return true;
        }

        boolean isBorrowed() {
            return borrowed;
        }

        int getBorrowCount() {
            return borrowCount;
        }

        String summary() {
            return title + " | borrowed=" + borrowed
                    + " | times=" + borrowCount;
        }

        static int getCreatedCount() {
            return createdCount;
        }
    }

    public static void main(String[] args) {
        System.out.println("initial created=" + Book.getCreatedCount());

        Book javaBook = new Book(" Java ");
        Book algoBook = new Book("Algorithms");
        System.out.println("created after new=" + Book.getCreatedCount());

        System.out.println("java start=" + javaBook.summary());
        System.out.println("algorithms start=" + algoBook.summary());
        System.out.println("borrow java=" + javaBook.borrow());
        System.out.println("borrow java again=" + javaBook.borrow());
        System.out.println("java after borrow=" + javaBook.summary());
        System.out.println("algorithms unchanged=" + algoBook.summary());

        System.out.println("return java=" + javaBook.returnBook());
        System.out.println("return java again=" + javaBook.returnBook());

        Book alias = javaBook;
        System.out.println("borrow alias=" + alias.borrow());
        System.out.println("alias same object=" + (alias == javaBook));
        System.out.println("java final=" + javaBook.summary());
        System.out.println("algorithms final=" + algoBook.summary());
        System.out.println("total created=" + Book.getCreatedCount());

        try {
            new Book(" ");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid title=" + ex.getMessage());
        }
        System.out.println("total after invalid=" + Book.getCreatedCount());
    }
}
~~~

**Yêu cầu:** JDK 17+; không cần thư viện ngoài, Maven, Gradle hoặc preview features. Mã dùng một `public class` có tên trùng tên file và một lớp `Book` lồng nhau để mọi thứ có thể chạy từ một file.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 FieldsMethodsDemo.java
java -cp . FieldsMethodsDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\FieldsMethodsDemo.java
java -cp . FieldsMethodsDemo
~~~

### Exact expected stdout

~~~text
initial created=0
created after new=2
java start=Java | borrowed=false | times=0
algorithms start=Algorithms | borrowed=false | times=0
borrow java=true
borrow java again=false
java after borrow=Java | borrowed=true | times=1
algorithms unchanged=Algorithms | borrowed=false | times=0
return java=true
return java again=false
borrow alias=true
alias same object=true
java final=Java | borrowed=true | times=2
algorithms final=Algorithms | borrowed=false | times=0
total created=2
invalid title=title must not be blank
total after invalid=2
~~~

**Giải thích từng pha:**

1. Khi mới chạy, `createdCount` mặc định bằng 0. Hai `new Book(...)` thành công khiến số đó thành 2.
2. `borrowed` và `borrowCount` là **instance fields** mặc định `false` và `0` cho **mỗi** đối tượng.
3. Mượn sách `Java` lần thứ nhất thành công; lần thứ hai bị từ chối, nên `times` vẫn bằng 1. Sách `Algorithms` không đổi.
4. Trả sách lần thứ nhất thành công, lần thứ hai trả `false` vì sách không còn được mượn.
5. `alias` và `javaBook` cùng chỉ đến một object; mượn qua `alias` khiến `javaBook.summary()` hiển thị `times=2`.
6. Constructor bị lỗi với tiêu đề toàn khoảng trắng **trước** dòng tăng bộ đếm, nên `createdCount` vẫn là 2.

## 10. Lỗi phổ biến

| Nhầm lẫn | Điều cần hiểu |
|---|---|
| Nghĩ field và method đều là “biến” | Field lưu dữ liệu; method là khai báo hành vi có thể được gọi |
| Tưởng `Book a;` đã tạo object | Đây chỉ là khai báo biến tham chiếu; cần `new Book(...)` |
| Nghĩ hai đối tượng cùng lớp chia sẻ mọi field | **Instance fields** là trạng thái từng object; **static fields** mới gắn với lớp |
| Viết `score = score;` khi tên tham số trùng field | Dùng `this.score = score;` để gán cho field |
| Cho mọi field thành `public` để sửa tùy ý | Có thể phá vỡ quy tắc của lớp; cân nhắc `private` và phương thức kiểm soát |
| Gọi method `borrow()` rồi coi giá trị trả về là field | Giá trị `boolean` được method tính/trả, không phải khai báo field mới |
| Gọi instance method từ `static main` mà không có object | Tạo/lấy tham chiếu object rồi gọi `book.borrow()` |
| Dùng `this` trực tiếp trong static method | Static context không có receiver instance |
| Nghĩ `final String title` khiến cả object bất biến | Chỉ field `title` không được gán lại; `borrowed` và `borrowCount` vẫn có thể thay đổi |
| Gán `Book alias = book;` rồi nghĩ có bản sao object | Chỉ sao chép giá trị tham chiếu, hai biến chỉ cùng object |

## 11. Bài tập có đáp án

**A.** Phân loại các thành viên sau:

~~~java
private int balance;
void deposit(int amount) { balance += amount; }
int getBalance() { return balance; }
~~~

**Đáp án:** `balance` là **instance field**; `deposit` là method **thay đổi trạng thái**; `getBalance` là method **đọc/trả trạng thái**.

**B.** Nếu tạo `Book first = new Book("A")` và `Book second = new Book("B")`, rồi chỉ gọi `first.borrow()`, trường `borrowed` của `second` là gì?  
**Đáp án:** `false`, vì đó là instance field riêng của `second`.

**C.** Vì sao `private boolean borrowed` giúp thiết kế hợp lý hơn `public boolean borrowed`?  
**Đáp án:** caller không thể tùy tiện gán field từ ngoài lớp, nên lớp có thể đảm bảo chuyển trạng thái qua `borrow()`/`returnBook()` đúng quy tắc.

**D.** `Book alias = first;` rồi `alias.borrow()` có tác động đối tượng `first` không?  
**Đáp án:** **Có**, vì hai tham chiếu cùng trỏ tới một đối tượng.

**E.** Một static method có gọi trực tiếp `this.summary()` được không?  
**Đáp án:** **Không**. Static method không có receiver instance mặc định; cần tham chiếu object cụ thể.

**F.** Tại sao lần tạo `new Book(" ")` của chương trình hoàn chỉnh không tăng `createdCount`?  
**Đáp án:** constructor ném `IllegalArgumentException` trong bước kiểm tra, trước khi thực hiện `createdCount++`.

## 12. Checklist và kết luận

- [ ] Biết **field lưu dữ liệu/trạng thái** và **method thể hiện hành vi**.
- [ ] Phân biệt khai báo lớp với tạo đối tượng bằng `new`.
- [ ] Nhận diện instance fields, instance methods và các thành viên `static`.
- [ ] Hiểu constructor thiết lập trạng thái ban đầu.
- [ ] Dùng `this.field` phân biệt field và tham số cùng tên.
- [ ] Hiểu method có thể đọc, cập nhật field và trả kết quả.
- [ ] Dùng `private` và hành vi có kiểm tra để giữ trạng thái hợp lệ.
- [ ] Phân biệt thay đổi trạng thái một object và thay đổi object khác.
- [ ] Biết alias là nhiều tham chiếu cùng một object, không phải bản sao mới.
- [ ] Đọc và đối chiếu exact stdout của `FieldsMethodsDemo.java` trên JDK 17+.

**Kết luận:** Lớp Java gom **dữ liệu** trong các field và **hành vi** trong các method. Field thể hiện trạng thái của từng object; method sử dụng và thay đổi trạng thái theo quy tắc của lớp. Thiết kế field `private`, constructor hợp lệ và những method có mục đích rõ ràng giúp chương trình dễ hiểu, an toàn và dễ mở rộng.