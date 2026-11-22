# `new` tạo đối tượng và trả về tham chiếu — Java 17+

## 1. Mục tiêu: phân biệt đối tượng với biến tham chiếu

Trong Java, biểu thức `new` dùng để **tạo một đối tượng mới** của lớp có thể khởi tạo (hoặc một mảng mới). Với việc tạo instance của class, Java cấp phát và khởi tạo đối tượng, thực thi constructor tương ứng; nếu quá trình thành công, **giá trị của biểu thức `new` là một tham chiếu tới đối tượng vừa tạo**.

~~~java
Person person = new Person("Lan");
~~~

Hãy tách câu lệnh trên thành ba ý:

1. `Person` là **kiểu khai báo của biến** `person`.
2. `new Person("Lan")` **tạo một instance** của `Person`, gọi constructor với đối số `"Lan"` và tạo ra giá trị tham chiếu đến instance ấy nếu thành công.
3. `=` **gán giá trị tham chiếu** này vào biến `person`.

Biến `person` **không phải bản thân đối tượng**. Nó giữ một giá trị tham chiếu giúp chương trình truy cập đối tượng.

~~~java
final class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    String getName() {
        return name;
    }
}

// Trong method:
Person person = new Person("Lan");
System.out.println(person.getName()); // Lan
~~~

Một biến tham chiếu có thể được **gán lại** để trỏ đến đối tượng khác; còn đối tượng đã tạo có thể có nhiều biến cùng tham chiếu tới nó.

## 2. `new` và constructor: ai làm việc gì?

Cú pháp cơ bản khi tạo đối tượng:

~~~java
ClassName variable = new ClassName(arguments);
~~~

- `new` mở đầu biểu thức tạo instance.
- `ClassName` xác định lớp được khởi tạo.
- Dấu `(...)` truyền đối số cho **constructor** phù hợp.
- Toàn bộ biểu thức `new ClassName(...)` có kiểu tham chiếu của instance vừa tạo (có thể gán vào biến có kiểu tương thích).

Ví dụ một lớp có hai constructor:

~~~java
final class Book {
    private final String title;
    private final int pages;

    Book(String title) {
        this(title, 0); // Gọi constructor khác cùng lớp
    }

    Book(String title, int pages) {
        this.title = title;
        this.pages = pages;
    }

    String describe() {
        return title + " (" + pages + " pages)";
    }
}

// Trong method:
Book first = new Book("Java");
Book second = new Book("Java", 120);
System.out.println(first.describe());  // Java (0 pages)
System.out.println(second.describe()); // Java (120 pages)
~~~

Constructor có **cùng tên lớp** và **không có kiểu trả về**, kể cả `void`. Không viết `new` trong định nghĩa constructor.

**Phân biệt:** constructor không phải một method thông thường “trả về đối tượng”; **biểu thức tạo instance `new`** mang giá trị tham chiếu sau khi constructor hoàn tất thành công.

### Có bắt buộc phải lưu vào biến không?

Không. Tham chiếu từ `new` là một giá trị biểu thức, nên có thể dùng trực tiếp:

~~~java
System.out.println(new Book("Direct", 20).describe());
// Direct (20 pages)
~~~

Với object cần dùng lại, nên giữ vào biến có tên rõ nghĩa để code dễ đọc.

## 3. Mỗi lần `new` riêng tạo một instance riêng biệt

~~~java
Person a = new Person("Lan");
Person b = new Person("Lan");

System.out.println(a == b); // false
~~~

Dù cả hai có nội dung `name` giống nhau, đó là **hai đối tượng khác nhau** vì chúng đến từ hai lần tạo instance bằng `new` riêng biệt.

So sánh biến tham chiếu bằng `==` kiểm tra **đồng nhất đối tượng** (*reference identity*): hai tham chiếu có chỉ cùng một object hay không. Nó **không so sánh tự động các field**.

| Câu lệnh | Số instance `Person` mới | Giá trị tham chiếu |
|---|---:|---|
| `Person a = new Person("Lan");` | 1 | `a` trỏ instance mới |
| `Person b = a;` | 0 | `b` sao chép tham chiếu từ `a` |
| `Person c = new Person("Lan");` | 1 | `c` trỏ instance khác |
| `b = c;` | 0 | `b` đổi sang tham chiếu của `c` |

**Quy tắc:** **phép gán tham chiếu không tạo bản sao đối tượng**. Muốn có đối tượng khác, cần tạo riêng hoặc dùng cơ chế sao chép phù hợp do API cung cấp.


## 4. Dùng kết quả của `new`

Kết quả `new Book("Java")` có thể gán ngay cho biến, trả về từ phương thức hoặc truyền trực tiếp làm đối số. Sau đó `Book alias = book;` chỉ sao chép tham chiếu, trong khi `alias = new Book("Khác");` mới thực hiện thêm một lần khởi tạo. Tham số phương thức nhận **bản sao giá trị tham chiếu**; gán lại tham số không gán lại biến của bên gọi. Muốn thay object ở phía gọi, hãy trả tham chiếu mới và để bên gọi chủ động gán.

## 5. `new` cho mảng: array object khác phần tử object

`new` cũng được dùng để tạo **mảng**:

~~~java
int[] numbers = new int[3];
System.out.println(numbers.length); // 3
System.out.println(numbers[0]);     // 0
~~~

`new int[3]` tạo một array object có 3 phần tử `int`, được khởi tạo mặc định bằng `0`.

Nhưng mảng tham chiếu chỉ tạo **mảng chứa các tham chiếu**, không tự tạo các đối tượng ở từng phần tử:

~~~java
Box[] slots = new Box[2];

System.out.println(slots.length); // 2
System.out.println(slots[0] == null); // true

slots[0] = new Box(50);
System.out.println(slots[0].value); // 50
~~~

Ở đây có **hai lần tạo** thuộc hai loại khác nhau:

- `new Box[2]` tạo **một mảng**, ban đầu hai phần tử tham chiếu đều `null`.
- `new Box(50)` tạo **một instance Box** riêng và gán tham chiếu cho `slots[0]`.

**Đừng nhầm** `new Box[2]` với “tự chạy constructor Box hai lần”.

## 6. Constructor và quá trình khởi tạo đối tượng

Khi thực thi `new ClassName(...)` hợp lệ, Java chuẩn bị một instance, áp dụng giá trị mặc định cho các field, thực hiện quy trình khởi tạo lớp/instance và lời gọi constructor theo quy tắc kế thừa/khởi tạo của ngôn ngữ.

Ví dụ ngắn:

~~~java
final class Ticket {
    int id; // Field ban đầu có giá trị mặc định 0

    Ticket(int id) {
        this.id = id;
    }
}

// Trong method:
Ticket ticket = new Ticket(42);
System.out.println(ticket.id); // 42
~~~

Những ý quan trọng:

- Field được khởi tạo theo quy tắc Java; constructor có thể gán giá trị riêng.
- Constructor có thể **ném exception**. Nếu quá trình khởi tạo thất bại, biểu thức `new` không hoàn tất bình thường để cung cấp một tham chiếu kết quả cho phép gán đó.
- `new` có thể gặp lỗi tài nguyên, ví dụ `OutOfMemoryError`; **không được coi mọi lần gọi new luôn thành công**.
- Constructor không bắt buộc chỉ gán field; nó có thể thực hiện validation và các logic khởi tạo khác. Tuy nhiên, nên giữ trạng thái đối tượng nhất quán và không phát tán `this` đang khởi tạo dở một cách tùy tiện.

Về mô hình bộ nhớ, object thường được nhắc tới là “nằm trên heap”, nhưng JVM/JIT có thể tối ưu cấp phát trong một số trường hợp. Điều quan trọng đối với logic nguồn Java là **ngữ nghĩa instance và identity**, không phải đoán một địa chỉ vật lý.


## 7. Quan sát object vừa tạo

`new Box(10) == new Box(10)` là `false` vì mỗi vế tạo instance riêng. `equals` chỉ so giá trị nếu class có định nghĩa hợp đồng tương ứng; mặc định `Object.equals` so identity. Không lấy chuỗi từ `Object.toString()` làm địa chỉ bộ nhớ: dạng `ClassName@hash` không bảo đảm là địa chỉ thực. Nếu cần in trạng thái dễ đọc, hãy tự định nghĩa `toString()` như ví dụ `Counter` bên dưới.

## 8. Chương trình Java 17 chạy độc lập

Tạo tệp chính xác **`NewReferenceDemo.java`** với nội dung:

~~~java
public final class NewReferenceDemo {
    private NewReferenceDemo() {}

    static final class Counter {
        static int created;

        private final String name;
        private int value;

        Counter(String name, int value) {
            this.name = name;
            this.value = value;
            created++;
        }

        void add(int amount) {
            value += amount;
        }

        @Override
        public String toString() {
            return name + "=" + value;
        }
    }

    static void mutate(Counter counter) {
        counter.add(2);
    }

    static void rebindParameter(Counter counter) {
        counter = new Counter("Local", 99);
        System.out.println("inside rebind=" + counter);
    }

    public static void main(String[] args) {
        Counter first = new Counter("A", 10);
        Counter alias = first;
        Counter other = new Counter("A", 10);

        System.out.println("first=" + first);
        System.out.println("alias same=" + (first == alias));
        System.out.println("other same=" + (first == other));

        alias.add(5);
        System.out.println("after alias first=" + first);
        System.out.println("other unaffected=" + other);

        alias = new Counter("B", 1);
        System.out.println("alias rebound=" + alias);
        System.out.println("first still=" + first);

        mutate(first);
        System.out.println("after method mutate=" + first);

        rebindParameter(first);
        System.out.println("after method rebind=" + first);

        Counter missing = null;
        System.out.println("missing is null=" + (missing == null));
        try {
            missing.add(1);
        } catch (NullPointerException ex) {
            System.out.println("null access=NullPointerException");
        }

        Counter[] slots = new Counter[2];
        System.out.println("slots length=" + slots.length);
        System.out.println("default slot null=" + (slots[0] == null));
        slots[0] = new Counter("Slot", 3);
        System.out.println("slot object=" + slots[0]);

        int[] numbers = new int[2];
        System.out.println("int defaults=" + numbers[0]
                + "," + numbers[1]);

        System.out.println("Counter instances created=" + Counter.created);
    }
}
~~~

Dùng **JDK 17+** và mở terminal tại thư mục chứa source.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 NewReferenceDemo.java
java -cp . NewReferenceDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\NewReferenceDemo.java
java -cp . NewReferenceDemo
~~~

**Expected output (không phụ thuộc địa chỉ/hash object):**

~~~text
first=A=10
alias same=true
other same=false
after alias first=A=15
other unaffected=A=10
alias rebound=B=1
first still=A=15
after method mutate=A=17
inside rebind=Local=99
after method rebind=A=17
missing is null=true
null access=NullPointerException
slots length=2
default slot null=true
slot object=Slot=3
int defaults=0,0
Counter instances created=5
~~~

### Giải thích cách đếm `new`

Biến `Counter.created` chỉ tăng ở **constructor `Counter(...)`**. Trong chương trình có 5 lần tạo instance `Counter`:

1. `first = new Counter("A", 10)`.
2. `other = new Counter("A", 10)`.
3. `alias = new Counter("B", 1)`.
4. `counter = new Counter("Local", 99)` bên trong method.
5. `slots[0] = new Counter("Slot", 3)`.

Các lệnh `alias = first`, `mutate(first)` và `new Counter[2]` **không tạo thêm instance Counter**. `new Counter[2]` chỉ tạo một **array object**. `new int[2]` cũng tạo một array object và các phần tử số có giá trị mặc định 0.

Phép `alias = new Counter(...)` và phép gán lại tham số trong `rebindParameter` **không làm biến `first` đổi tham chiếu**. Chỉ `mutate(first)` sửa trạng thái đối tượng mà `first` đang trỏ tới.


## 9. Kiểm tra đúng ý nghĩa biểu thức tạo đối tượng

- `new SomeType[n]` luôn tạo mảng nếu thành công; với kiểu phần tử tham chiếu, các phần tử ban đầu bằng `null` và **chưa tạo** `SomeType`.
- Nếu constructor ném exception, biểu thức tạo instance không hoàn tất bình thường nên phép gán kết quả không xảy ra.
- Biểu thức `new` cũng có thể thất bại do tài nguyên; không dựa trên giả định mọi lần khởi tạo đều thành công.
- `new` trả giá trị tham chiếu, còn constructor không khai báo kiểu trả về; phân biệt hai ý này khi đọc mã.


## 10. Bài tập tập trung vào `new`

**Bài A.** `Book a = new Book("A"); Book b = a; Book c = new Book("A");` thực hiện bao nhiêu lần tạo instance `Book`?

*Đáp án:* Hai. Phép `b = a` không gọi constructor.

**Bài B.** `Book[] shelf = new Book[3]; shelf[0] = new Book("B");` tạo bao nhiêu đối tượng mảng và bao nhiêu `Book`?

*Đáp án:* Một mảng và một `Book`. Hai phần tử còn lại vẫn bằng `null`.

**Bài C.** Nếu `new Book(null)` gọi constructor có `Objects.requireNonNull(title)` rồi ném `NullPointerException`, biến nhận kết quả của phép gán có được cập nhật không?

*Đáp án:* Không. Khi constructor thất bại, phép gán không được thực hiện. Nếu là biến cục bộ trước đó chưa được gán, sau nhánh thất bại vẫn phải tuân thủ quy tắc *definite assignment*.

## 11. Checklist và kết luận

- [ ] Phân biệt **instance object** với **biến tham chiếu**.
- [ ] Hiểu `new ClassName(...)` tạo instance, chạy constructor và tạo giá trị tham chiếu nếu thành công.
- [ ] Phân biệt `new ClassName(...)` với `ClassName other = existing;`.
- [ ] Biết `==` so **cùng object** khi áp dụng cho hai tham chiếu.
- [ ] Nhận ra hai biến alias có thể sửa cùng một object.
- [ ] Hiểu phép gán lại một biến không tự sửa object mà biến đó từng trỏ.
- [ ] Phân biệt biến cục bộ chưa gán, tham chiếu `null` và tham chiếu tới object.
- [ ] Biết `new SomeClass[n]` tạo **mảng**, không tự tạo `n` instance của class.
- [ ] Hiểu Java truyền tham chiếu theo **giá trị**, không pass-by-reference.
- [ ] Không suy ra địa chỉ vật lý hoặc thời điểm GC từ biểu thức `new`.
- [ ] Biên dịch và chạy `NewReferenceDemo.java`, đối chiếu từng dòng output.

**Kết luận:** `new` là biểu thức **tạo instance và cho kết quả là tham chiếu** khi khởi tạo thành công. Gán tham chiếu không nhân bản object; nhiều biến có thể cùng trỏ một instance, còn mỗi biểu thức tạo instance `new ClassName(...)` thực thi riêng biểu thị một lần tạo instance riêng. Hiểu rõ điều này giúp xử lý đúng identity, alias, tham số method, `null` và vòng đời đối tượng trong Java 17+.