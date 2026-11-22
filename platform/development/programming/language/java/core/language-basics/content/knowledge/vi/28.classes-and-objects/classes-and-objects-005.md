# `this` biểu thị đối tượng hiện tại — Java 17+

## 1. `this` là gì?

Trong **constructor, phương thức instance và ngữ cảnh instance** của một lớp Java, `this` là biểu thức tham chiếu tới **chính đối tượng hiện tại**. Đó là đối tượng được khởi tạo hoặc đối tượng nhận lời gọi phương thức.

~~~java
class Box {
    private int value;

    Box(int value) {
        this.value = value;
    }

    void increase() {
        this.value++;
    }

    int getValue() {
        return this.value;
    }
}
~~~

Nếu tạo hai hộp riêng bằng `new Box(1)` và `new Box(10)`, rồi gọi `increase()` trên hộp đầu, `this` trong lượt gọi ấy chỉ **hộp đầu**. Trong lượt gọi `increase()` trên hộp thứ hai, `this` lại chỉ **hộp thứ hai**.

**Nhớ:** `this` không phải tên lớp, không tạo object, và không phải biến có thể gán lại; nó biểu thị **instance hiện tại**. `this` không được dùng trực tiếp trong ngữ cảnh `static`.

## 2. `this.field`: phân biệt field với tham số hoặc local

~~~java
class Student {
    private String name;

    Student(String name) {
        this.name = name;
    }
}
~~~

Trong `Student(String name)`:

- `name` ở vế phải là **tham số constructor**.
- `this.name` ở vế trái là **field của đối tượng đang tạo**.
- Không có `this`, lệnh `name = name;` chỉ gán tham số cho chính nó; field chưa được cập nhật như mong muốn.

| Biểu thức | Ý nghĩa |
|---|---|
| `name` | Tên đơn; nếu có tham số/local cùng tên, Java dùng tham số/local đó |
| `this.name` | Field `name` của instance hiện tại |
| `this.score` | Field `score` của instance hiện tại |
| `this.getScore()` | Gọi phương thức instance trên instance hiện tại |

Nếu không có biến local/tham số nào che tên field, `score` và `this.score` thường cùng chỉ field của đối tượng đó. Dùng `this` khi cần phân biệt, hoặc khi muốn thể hiện rõ đây là thành viên instance.

## 3. `this.method()` và lời gọi ngầm

Trong một instance method:

~~~java
void addPoints(int amount) {
    this.points += amount;
}

void addAndPrint(int amount) {
    this.addPoints(amount);
    System.out.println(this.points);
}
~~~

Nếu `addPoints` là instance method cùng lớp, có thể viết ngắn `addPoints(amount);`; lời gọi không định danh đối tượng vẫn được thực hiện trên instance hiện tại (trong các trường hợp thông thường).

`this.addPoints(amount)` **không gọi phương thức của một instance mới**. Nó gọi phương thức với cùng receiver `this` hiện có. Khi gọi `an.addAndPrint(5)`, các lần truy cập `this.points` ở hai phương thức đều thuộc object mà `an` trỏ tới.

Không dùng `this` làm cách thay thế cho việc chọn object khác. Muốn thay đổi `binh`, phải gọi trên object `binh` hoặc có tham chiếu rõ ràng tới nó.

## 4. `this(...)` là lời gọi constructor khác

Phân biệt hai cú pháp:

- `this.field`, `this.method()`: dùng **đối tượng hiện tại**.
- `this(arguments);`: gọi **constructor khác trong cùng lớp** để dùng lại logic khởi tạo.

~~~java
class Student {
    private String name;
    private int score;

    Student(String name) {
        this(name, 0);  // Constructor chaining.
    }

    Student(String name, int score) {
        this.name = name;
        this.score = score;
    }
}
~~~

Trên Java 17, một lời gọi constructor tường minh `this(...)` phải là **câu lệnh đầu tiên trong thân constructor**. Không đặt lệnh in, phép gán field hoặc `this.field` trước lời gọi ấy. Một constructor không thể vừa gọi `this(...)` vừa gọi `super(...)` tường minh; chuỗi gọi constructor cũng không được tạo vòng lặp vô hạn giữa các constructor.

`this(name, 0)` **không tạo thêm một Student thứ hai**. Nó thực hiện constructor hai tham số để khởi tạo **cùng object đang được tạo**. Việc tạo object xuất phát từ `new Student(...)`.

## 5. `return this`: trả tham chiếu của chính object

~~~java
class Counter {
    private int count;

    Counter add(int amount) {
        this.count += amount;
        return this;
    }

    int getCount() {
        return this.count;
    }
}
~~~

Có thể viết:

~~~java
Counter counter = new Counter();
Counter returned = counter.add(2).add(3);
System.out.println(counter.getCount());
System.out.println(counter == returned);
~~~

**Exact expected stdout:**

~~~text
5
true
~~~

`return this;` trả **tham chiếu tới chính object đang nhận lời gọi**, không tạo bản sao. Kiểu trả về ở ví dụ là `Counter`, không phải `void`; vì thế mới trả được `this`. Cách trả về này thường dùng trong *fluent API* hoặc *method chaining*, nhưng chỉ nên áp dụng khi làm API rõ ràng.


## 6. Cùng instance thì `this` cũng là cùng receiver

~~~java
Counter first = new Counter();
Counter alias = first;
first.add(1);
alias.add(2);
System.out.println(first.getCount()); // 3
System.out.println(first == alias);    // true
~~~

Hai biến `first` và `alias` cùng tham chiếu một object. Vì thế trong cả hai lần gọi `add`, `this` vẫn chỉ **object Counter ấy**. Khi `alias = new Counter()`, lời gọi tiếp theo qua `alias` sẽ có receiver khác. `this` không phải biến có thể gán lại, và `return this` không sao chép đối tượng. Trường hợp nhiều object và alias được minh họa đầy đủ ở bài đầu chương.

## 7. Khi nào `this` không hợp lệ?

`this` chỉ có ý nghĩa khi có **instance hiện tại**. Phương thức `static` gắn với lớp, không có một receiver instance mặc định:

~~~java
class Student {
    private int score;

    static void invalid() {
        // System.out.println(this.score);
        // LỖI BIÊN DỊCH: không dùng this trong static context.
    }
}
~~~

Cách đúng là nhận hoặc tạo một object rồi truy cập qua tham chiếu đó (tuân thủ phạm vi và quyền truy cập):

~~~java
static int readScore(Student student) {
    return student.score;  // Đọc qua tham chiếu student, không phải this.
}
~~~

Ngoài ra:

- Không thể `this = anotherObject;` vì `this` không phải biến gán được.
- Trong `main` là phương thức static, dùng `student.method()` hoặc `new Student(...)`, không dùng `this.method()`.
- `this` trong một instance method luôn tham chiếu **receiver hiện tại**. Khi có kế thừa, receiver thực tế có thể thuộc lớp con; `super` là cách chọn phiên bản thành viên của lớp cha trong ngữ cảnh thích hợp, khác với `this`.

## 8. Chương trình Java 17+ tự chạy bằng CLI

Lưu file **`ThisCurrentObjectDemo.java`**:

~~~java
public final class ThisCurrentObjectDemo {
    private ThisCurrentObjectDemo() {}

    static final class Student {
        private final String name;
        private int points;

        Student(String name) {
            this(name, 0); // Phải đứng đầu constructor trong Java 17.
        }

        Student(String name, int points) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("invalid name");
            }
            if (points < 0 || points > 100) {
                throw new IllegalArgumentException("invalid points");
            }
            this.name = name.strip();
            this.points = points;
        }

        void addPoints(int delta) {
            if (delta <= 0 || delta > 100 - this.points) {
                throw new IllegalArgumentException("points out of range");
            }
            this.points += delta;
        }

        Student addAndReturnThis(int delta) {
            this.addPoints(delta);
            return this;
        }

        boolean sameObject(Student other) {
            return this == other;
        }

        String describe() {
            return this.name + ":" + this.points;
        }

        static String classLabel() {
            return "Student";
        }
    }

    public static void main(String[] args) {
        Student an = new Student(" An ", 70);
        Student binh = new Student("Binh");

        System.out.println("an=" + an.describe());
        System.out.println("binh=" + binh.describe());

        an.addPoints(5);
        System.out.println("an after direct=" + an.describe());
        System.out.println("binh unchanged=" + binh.describe());

        Student alias = an;
        alias.addPoints(5);
        System.out.println("an via alias=" + an.describe());
        System.out.println("alias same an=" + alias.sameObject(an));
        System.out.println("an same binh=" + an.sameObject(binh));

        Student returned = an.addAndReturnThis(10);
        System.out.println("returned same an=" + (returned == an));
        System.out.println("an after return this=" + an.describe());

        binh.addPoints(20);
        System.out.println("binh after add=" + binh.describe());

        Student sameData = new Student("An", 90);
        System.out.println("same data same object=" + (an == sameData));
        System.out.println("static label=" + Student.classLabel());

        try {
            an.addPoints(11);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid add=" + ex.getMessage());
        }
        System.out.println("an final=" + an.describe());
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 ThisCurrentObjectDemo.java
java -cp . ThisCurrentObjectDemo
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\ThisCurrentObjectDemo.java
java -cp . ThisCurrentObjectDemo
~~~

### Exact expected stdout

~~~text
an=An:70
binh=Binh:0
an after direct=An:75
binh unchanged=Binh:0
an via alias=An:80
alias same an=true
an same binh=false
returned same an=true
an after return this=An:90
binh after add=Binh:20
same data same object=false
static label=Student
invalid add=points out of range
an final=An:90
~~~

**Lưu ý tràn số:** Vì `this.points` được giữ trong `0..100`, dùng `delta > 100 - this.points` thay vì cộng trước khi so sánh; nhờ đó `Integer.MAX_VALUE` không thể làm `int` tràn rồi vượt qua kiểm tra.

**Đọc kết quả:** `this` trong `an.addPoints` là object của `an`, không phải `binh`; qua biến `alias` vẫn là object ấy. `this(...)` trong constructor một tham số thiết lập điểm mặc định bằng 0 trên cùng instance `binh`. `return this` trả đúng tham chiếu `an`, không cấp phát object mới.

## 9. Bài tập, lỗi hay gặp và checklist

| Sai lầm | Vì sao sai? | Cách sửa |
|---|---|---|
| `name = name;` khi tham số trùng tên field | Chỉ tác động tham số | `this.name = name;` |
| Nghĩ `this` tạo thêm instance | `this` chỉ instance sẵn có | `new` mới tạo object |
| Dùng `this.field` trong `static` | Không có receiver instance | Dùng object cụ thể |
| Viết lệnh trước `this(...)` trong constructor Java 17 | Vi phạm quy tắc lời gọi constructor đầu tiên | Đặt `this(...)` đầu thân constructor |
| Cho rằng `return this` tạo bản sao | Trả chính tham chiếu object | Tạo bản sao rõ ràng nếu cần |
| Cho rằng `alias = a` tạo object mới | Chỉ sao chép tham chiếu | Phân biệt alias với `new` |

**Bài A:** Với `Student a = new Student("An", 10);` và `Student b = a;`, lời gọi `b.addPoints(5)` làm `a.describe()` trả gì? **`An:15`**: `this` của lời gọi trỏ cùng object.

**Bài B:** Có thể dùng `this` trong `public static void main` không? **Không**. Phải có một object, ví dụ `Student a = new Student("An"); a.describe();`.

**Bài C:** `Student(String name) { this(name, 0); }` tạo mấy Student khi gọi `new Student("An")`? **Một**. Nó gọi constructor khác cho cùng object, không gọi `new` lần thứ hai.

**Bài D:** `return this;` có giống `return new Student(...);` không? **Không**. Một bên trả object đang có; bên còn lại tạo object khác.

### Checklist

- [ ] Hiểu `this` là object hiện tại trong ngữ cảnh instance.
- [ ] Biết `this.field` phân biệt field với tham số/local cùng tên.
- [ ] Biết `this.method()` gọi method trên chính instance ấy.
- [ ] Phân biệt `this(...)` (constructor chaining) với `this.field`.
- [ ] Nhớ trong Java 17, `this(...)` phải là lệnh đầu tiên của constructor.
- [ ] Hiểu `return this` trả cùng tham chiếu, không copy object.
- [ ] Hiểu hai biến alias có thể có cùng receiver `this`.
- [ ] Không dùng `this` trong static context.
- [ ] Biên dịch và chạy `ThisCurrentObjectDemo.java`, đối chiếu exact stdout.

**Kết luận:** `this` luôn giúp xác định **đối tượng hiện tại** trong code instance. Dùng `this.field` để truy cập field, `this.method()` để gọi hành vi trên receiver, `this(...)` để tái sử dụng constructor và `return this` để trả chính instance ấy.