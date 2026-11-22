# Phân biệt khai báo lớp, biến tham chiếu và thể hiện của lớp trong Java

Trong Java, ba khái niệm **lớp (class)**, **biến tham chiếu (reference variable)** và **thể hiện/đối tượng (instance/object)** liên quan chặt chẽ nhưng **không phải một**. Hiểu đúng sự khác biệt giúp đọc chính xác lệnh `Person p = new Person("An");`, dự đoán việc sửa dữ liệu qua nhiều biến, tránh `NullPointerException` và phân biệt kiểu khai báo với đối tượng thực tế khi dùng kế thừa.

## 1. Nhìn nhanh ba khái niệm

| Khái niệm | Là gì? | Ví dụ | Có tạo đối tượng `Person` mới không? |
| --- | --- | --- | --- |
| **Khai báo lớp** | Định nghĩa một kiểu tham chiếu và các thành phần của kiểu: thuộc tính, phương thức, constructor, ... | `class Person { ... }` | **Không** |
| **Khai báo biến tham chiếu** | Khai báo một biến có kiểu tham chiếu; biến có thể giữ một tham chiếu tới đối tượng tương thích hoặc `null` | `Person p;` | **Không** |
| **Tạo thể hiện của lớp** | Khởi tạo một đối tượng mới của lớp, thường bằng `new` và constructor | `new Person("An")` | **Có** |

Ba dòng dưới đây biểu diễn ba việc khác nhau:

```java
class Person { }       // 1. Khai báo lớp Person
Person p;              // 2. Khai báo biến tham chiếu p (trong một phương thức)
p = new Person();      // 3. Tạo một thể hiện rồi gán tham chiếu vào p
```

Đoạn trên dùng để minh họa cú pháp; hai lệnh cuối phải nằm trong một ngữ cảnh được Java cho phép (chẳng hạn thân phương thức), không được đặt tùy ý trực tiếp vào thân lớp.

**Công thức đọc:** `Person p = new Person();` kết hợp **khai báo biến** (`Person p`), **tạo đối tượng** (`new Person()`) và **phép gán tham chiếu** (`=`). Trong biểu thức đó, `Person` bên trái xác định kiểu của biến, còn `Person` sau `new` xác định lớp cần khởi tạo.

## 2. Khai báo lớp: mô tả kiểu và hành vi

```java
class Person {
    String name;                    // trường dữ liệu của từng đối tượng
    static int totalCreated = 0;    // trường static thuộc lớp

    Person(String name) {           // constructor: tên trùng tên lớp, không có kiểu trả về
        this.name = name;
        totalCreated++;
    }

    void introduce() {
        System.out.println("Mình là " + name);
    }
}
```

- `class Person` định nghĩa kiểu tên `Person`. Từ đó mã nguồn có thể khai báo biến kiểu `Person`, gọi constructor hoặc dùng thành phần có quyền truy cập phù hợp.
- `name` là **instance field**: mỗi đối tượng `Person` có trạng thái `name` của riêng mình. Từ khóa `this` trong phương thức/constructor thể hiện đối tượng đang được thao tác.
- `introduce()` là **instance method**: khi gọi `p.introduce()`, phương thức hoạt động trên đối tượng mà `p` đang tham chiếu.
- `totalCreated` là **static field**: thành phần của lớp, được chia sẻ giữa các thể hiện; truy cập rõ ràng bằng `Person.totalCreated`. Giá trị này do constructor tăng lên trong ví dụ, không phải bộ đếm đối tượng còn sống.

**Khai báo lớp không đồng nghĩa tạo đối tượng.** Định nghĩa `Person` chỉ cung cấp kiểu và các quy tắc tạo/sử dụng đối tượng. Java cũng có thành phần `static` có thể sử dụng mà không cần tạo một thể hiện `Person`, tùy quyền truy cập. Constructor được gọi khi có thao tác tạo thể hiện tương ứng.

Tên lớp thường viết theo `UpperCamelCase` (`Person`, `BankAccount`), tên biến theo `lowerCamelCase` (`person`, `currentAccount`). Đây là quy ước đặt tên, không phải sự khác biệt về bản chất giữa lớp và biến.

## 3. Biến tham chiếu: biến giữ một giá trị tham chiếu

```java
Person first;                 // chỉ khai báo biến cục bộ
Person second = null;         // biến có giá trị null: không tham chiếu đối tượng nào
first = new Person("An");     // first nhận tham chiếu tới một đối tượng mới
Person alias = first;         // sao chép giá trị tham chiếu, KHÔNG tạo Person mới
```

Điểm cần nhớ:

1. **Kiểu khai báo** (`Person`) quy định những thao tác được phép ở thời điểm biên dịch. **Tên biến** (`first`) là tên để truy cập giá trị tham chiếu được lưu trong biến.
2. Giá trị tham chiếu biểu thị đối tượng mà biến đang trỏ tới theo nghĩa logic. Java không cung cấp toán tử địa chỉ/con trỏ kiểu C/C++ để thao tác trực tiếp địa chỉ bộ nhớ của đối tượng.
3. Nhiều biến có thể giữ tham chiếu tới **cùng một đối tượng**. Phép gán `alias = first` sao chép giá trị tham chiếu, không sao chép đối tượng và không gọi constructor.
4. Một biến tham chiếu có thể được **gán lại** để tham chiếu một đối tượng khác hoặc `null` (trừ các ràng buộc như biến `final`).
5. Khi một đối tượng không còn được tham chiếu từ các đường dẫn còn đạt tới (reachable) thích hợp, nó có thể đủ điều kiện cho garbage collection; việc thu gom và thời điểm thu gom không được bảo đảm ngay lập tức.

**Lưu ý quan trọng về biến chưa khởi tạo:** với biến cục bộ `Person first;`, Java yêu cầu biến phải được gán giá trị xác định trước khi đọc. Không được suy ra rằng nó tự động là `null`. Trái lại, trường tham chiếu của đối tượng và trường `static` không được khởi tạo tường minh sẽ nhận giá trị mặc định `null`.

## 4. Thể hiện (instance): đối tượng cụ thể được khởi tạo

Xét:

```java
Person an = new Person("An");
Person binh = new Person("Bình");
```

Mỗi lần thực thi biểu thức `new Person(...)` bình thường tạo **một đối tượng `Person` mới**, tiến hành các bước khởi tạo và gọi constructor tương ứng. Sau đó biểu thức `new` cho một giá trị tham chiếu tới đối tượng vừa tạo; phép gán lưu tham chiếu ấy vào biến.

Ở ví dụ trên có **một lớp `Person`**, **hai biến tham chiếu** `an` và `binh`, và **hai thể hiện** khác nhau. Cả hai đều tuân theo định nghĩa lớp nhưng có trạng thái `name` riêng:

```text
Biến an   ──────────> đối tượng Person #1 { name: "An" }
Biến binh ──────────> đối tượng Person #2 { name: "Bình" }
                (cùng kiểu Person, khác danh tính)
```

Các nhãn `#1` và `#2` trong sơ đồ chỉ để phân biệt danh tính đối tượng; đó **không phải địa chỉ bộ nhớ** hoặc thuộc tính thật của `Person`.

Một đối tượng **không bắt buộc có một biến riêng** gắn với nó. Chẳng hạn `new Person("An").introduce();` tạo đối tượng, gọi phương thức qua tham chiếu tạm rồi không giữ tham chiếu ấy trong một biến do ta khai báo.

## 5. Ví dụ đầy đủ: lớp, biến tham chiếu, đối tượng và alias

Lưu toàn bộ mã sau vào tệp **`Demo.java`**:

```java
class Person {
    String name;
    static int totalCreated = 0;

    Person(String name) {
        this.name = name;
        totalCreated++;
    }

    void introduce() {
        System.out.println("Mình là " + name);
    }
}

public class Demo {
    public static void main(String[] args) {
        Person p;                         // khai báo biến, chưa tạo đối tượng
        p = new Person("An");             // đối tượng thứ nhất
        Person same = p;                  // thêm biến trỏ tới cùng đối tượng
        Person other = new Person("Bình");// đối tượng thứ hai

        same.name = "Lan";                // thay đổi đối tượng được chia sẻ
        p.introduce();
        System.out.println(p == same);
        System.out.println(p == other);
        System.out.println(Person.totalCreated);

        p = other;                        // đổi tham chiếu của p, không sửa same
        p.introduce();
        same.introduce();
        System.out.println(p == same);
    }
}
```

Biên dịch và chạy (Java 17 trở lên; mã cũng sử dụng cú pháp Java cơ bản):

```bash
javac -encoding UTF-8 Demo.java
java Demo
```

Kết quả chuẩn:

```text
Mình là Lan
true
false
2
Mình là Bình
Mình là Lan
false
```

Giải thích theo từng giai đoạn:

- `class Person` khai báo **một kiểu**. Hai lần `new Person(...)` thực thi tạo **hai đối tượng**, làm `Person.totalCreated` tăng thành `2`.
- `p`, `same`, `other` là **ba biến tham chiếu**. Sau `Person same = p;`, cả `p` lẫn `same` đều trỏ tới đối tượng ban đầu có tên `"An"`.
- Lệnh `same.name = "Lan";` sửa **trạng thái của đối tượng**, vì vậy gọi `p.introduce()` cũng in `Mình là Lan`.
- `p == same` ban đầu là `true` vì cùng tham chiếu một đối tượng; `p == other` là `false` vì hai đối tượng khác nhau.
- `p = other;` **chỉ đổi giá trị tham chiếu của biến `p`**. Nó không chuyển dữ liệu từ đối tượng này sang đối tượng kia và không thay đổi biến `same`; vì vậy lần gọi sau cho `p` in `Bình`, còn `same` vẫn in `Lan`.

Sơ đồ logic sau khi chạy `Person same = p;` và trước `p = other;`:

```text
p      ────┐
           ├────> Person #1 { name: "Lan" }
same   ────┘
other  ─────────> Person #2 { name: "Bình" }
```

Sau `p = other;`:

```text
same   ─────────> Person #1 { name: "Lan" }
p      ────┐
           ├────> Person #2 { name: "Bình" }
other  ────┘
```

**Câu hỏi tự kiểm tra:** Có bao nhiêu lần tạo đối tượng `Person` trong `main`? **Hai**, vì chỉ có hai lần thực thi `new Person(...)`. Có bao nhiêu biến tham chiếu `Person` được khai báo trong `main`? **Ba**: `p`, `same`, `other`. Số biến không quyết định số đối tượng.

## 6. Phân biệt kiểu nguyên thủy, tham chiếu `null` và biến chưa gán

| Mã | Ý nghĩa | Hệ quả |
| --- | --- | --- |
| `int number = 7;` | `int` là kiểu nguyên thủy; biến trực tiếp chứa giá trị `7` | `int other = number;` sao chép giá trị số |
| `Person p;` | Khai báo biến tham chiếu cục bộ, chưa gán | Không được đọc `p` trước khi gán |
| `Person p = null;` | Tham chiếu đã được gán giá trị đặc biệt `null` | Chưa tạo thể hiện `Person` nào |
| `Person p = new Person("An");` | Tạo thể hiện và lưu tham chiếu | Có một đối tượng mới |
| `Person q = p;` | Sao chép tham chiếu từ `p` sang `q` | `p` và `q` có thể cùng trỏ một đối tượng |

Cú pháp minh họa **không phải chương trình độc lập**:

```java
Person p;
System.out.println(p);       // Lỗi biên dịch: variable p might not have been initialized
```

Trong khi đó:

```java
Person p = null;
System.out.println(p);       // In: null
// p.introduce();            // Nếu bỏ comment sẽ ném NullPointerException khi chạy
```

Ví dụ `null` không khởi tạo đối tượng; việc gọi instance method hoặc truy cập instance field qua tham chiếu `null` dẫn đến `NullPointerException` (trừ một số trường hợp như cú pháp truy cập thành viên `static` được phân giải theo kiểu; hãy truy cập static qua tên lớp). Cách phòng tránh là thiết kế dữ liệu tránh `null` không cần thiết hoặc kiểm tra `p != null` trước khi truy cập khi `null` là trạng thái hợp lệ.

Không đồng nhất **khai báo**, **gán giá trị** và **khởi tạo đối tượng**. Những hành động này có thể xuất hiện trên một dòng, nhưng bản chất độc lập.

## 7. Dùng một phép thử để tách danh tính và nội dung

Sau khi đọc cú pháp khai báo biến và tạo instance, cần thêm một phép thử để tránh suy luận nhầm: **hai lần `new` thành công tạo hai objects khác nhau** ngay cả khi những dữ liệu nhìn thấy giống hệt.

~~~java
Person first = new Person("An");
Person second = new Person("An");
Person alias = first;
System.out.println(first == second);          // false
System.out.println(first == alias);           // true
System.out.println(first.name.equals(second.name)); // true
~~~

Đây là **snippet** dùng Person đã khai báo ở mục 2, cần đặt trong method. `first == second` kiểm tra cùng instance; so sánh nội dung `name` kiểm tra giá trị String; `alias` chỉ sao chép reference. Trong class Person chưa override `equals`, lời gọi `first.equals(second)` cũng false do mặc định của Object.

Bài này chỉ dùng các phép thử để **nhận diện thứ gì được khai báo, thứ gì thực sự được tạo và thứ gì đang được chia sẻ**. Việc thiết kế `equals/hashCode` theo value hoặc business identity là một quyết định sâu hơn, không tự xuất hiện từ cú pháp `new` hay tên biến.

## 8. Kiểu khai báo của biến có thể khác lớp thực tế của đối tượng

Với kế thừa/đa hình, kiểu biến ở phía trái có thể là lớp cha hoặc interface, còn thể hiện ở phía phải là lớp con tương thích. Đây là tình huống làm rõ nhất vì sao **kiểu biến** và **đối tượng đang được tham chiếu** không nên bị đánh đồng.

Lưu mã sau vào **`ReferenceTypeDemo.java`**:

```java
class Animal {
    void sound() {
        System.out.println("Âm thanh chung");
    }
}

class Dog extends Animal {
    @Override
    void sound() {
        System.out.println("Gâu");
    }

    void fetch() {
        System.out.println("Nhặt bóng");
    }
}

public class ReferenceTypeDemo {
    public static void main(String[] args) {
        Animal animal = new Dog();
        animal.sound();
        System.out.println(animal instanceof Dog);

        if (animal instanceof Dog dog) {
            dog.fetch();
        }
    }
}
```

```bash
javac -encoding UTF-8 ReferenceTypeDemo.java
java ReferenceTypeDemo
```

Kết quả:

```text
Gâu
true
Nhặt bóng
```

Trong `Animal animal = new Dog();`:

- `Animal` là **kiểu khai báo** (kiểu tĩnh) của biến `animal`.
- `animal` là **biến tham chiếu**, giữ tham chiếu đến một thể hiện.
- `new Dog()` tạo **đối tượng có lớp thực tế `Dog`**; không tạo thêm đối tượng `Animal` riêng biệt.
- `animal.sound()` hợp lệ vì `Animal` khai báo phương thức `sound()`; phiên bản override của `Dog` chạy nhờ phân phối động (dynamic dispatch).
- `animal.fetch()` không biên dịch, vì kiểu khai báo `Animal` không cung cấp `fetch()`. Kiểm tra `instanceof` với pattern `Dog dog` (hỗ trợ chính thức từ Java 16) cung cấp tham chiếu có kiểu `Dog` trong nhánh đúng để gọi `fetch()` an toàn.

Điều này không biến mọi đối tượng thành mọi kiểu: một biến chỉ có thể nhận giá trị tham chiếu có kiểu **tương thích theo quy tắc của Java**.

## 9. `final` và truyền tham số: vẫn phải phân biệt biến với đối tượng

**Tham chiếu `final`:** 

```java
final Person p = new Person("An");
p.name = "Lan";                 // Hợp lệ: sửa field của đối tượng
// p = new Person("Bình");      // Lỗi biên dịch: không thể gán lại biến final
```

`final` ràng buộc **biến tham chiếu `p` không được gán lại sau khi đã khởi tạo**, không tự động biến đối tượng mà nó tham chiếu thành bất biến. Bất biến (immutability) cần thiết kế lớp và trạng thái thích hợp.

**Java truyền tham số theo giá trị (pass-by-value)**, kể cả khi giá trị đó là tham chiếu. Xét đoạn minh họa bên trong cùng lớp có thể truy cập `Person`:

```java
static void rename(Person target) {
    target.name = "Lan";         // tác động lên đối tượng bên ngoài
}

static void replace(Person target) {
    target = new Person("Khác"); // chỉ gán lại biến tham số cục bộ
}
```

Khi gọi `rename(p)`, tham số `target` nhận **bản sao giá trị tham chiếu**, do đó thay đổi `target.name` cũng được quan sát qua `p`. Khi gọi `replace(p)`, việc gán lại `target` không tự gán lại biến `p` của nơi gọi. Đây là hệ quả trực tiếp của việc biến tham chiếu và đối tượng là hai thực thể khác nhau.

## 10. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Khai báo `class Person` đã tạo một `Person`.” | Khai báo lớp định nghĩa kiểu; tạo thể hiện là thao tác khác. |
| “`Person p;` tự tạo một `Person`.” | Chỉ khai báo biến; biến cục bộ còn chưa có giá trị để đọc. |
| “`Person p = null;` nghĩa là có đối tượng rỗng.” | `null` nghĩa là không có đối tượng nào được tham chiếu qua `p`. |
| “`Person q = p;` sao chép tất cả field để tạo một đối tượng mới.” | Chỉ sao chép giá trị tham chiếu; hai biến có thể cùng trỏ một đối tượng. |
| “Gán `p = other;` sẽ thay đổi nội dung đối tượng cũ.” | Nó đổi tham chiếu của `p`; trạng thái đối tượng cũ chỉ thay đổi nếu có thao tác sửa đối tượng ấy. |
| “Có ba biến tham chiếu thì phải có ba đối tượng.” | Số biến và số đối tượng độc lập; một đối tượng có thể có nhiều tham chiếu. |
| “Hai đối tượng có field giống nhau thì `a == b` là `true`.” | `==` kiểm tra danh tính đối tượng đối với kiểu tham chiếu. |
| “`final Person p` tạo ra một Person bất biến.” | `final` cấm gán lại `p`; tính bất biến của đối tượng phụ thuộc thiết kế lớp. |
| “Kiểu biến luôn đúng bằng lớp thực tế của đối tượng.” | `Animal animal = new Dog();` cho thấy kiểu khai báo và kiểu runtime có thể khác. |
| “Mất một tham chiếu thì đối tượng bị thu gom ngay.” | Đối tượng có thể còn tham chiếu khác; garbage collection không có thời điểm bảo đảm. |

## 11. Tự luyện đọc mã và kiểm tra hiểu đúng

Dựa trên lớp `Person` trong mục 5, hãy dự đoán số đối tượng và kết quả trước khi đọc lời giải:

```java
Person a = new Person("Một");
Person b = a;
Person c = new Person("Hai");

b.name = "Đã đổi";
a = c;

System.out.println(b.name);
System.out.println(a.name);
System.out.println(a == c);
System.out.println(a == b);
```

**Đáp án:** Hai thể hiện `Person` được tạo. In lần lượt:

```text
Đã đổi
Hai
true
false
```

Lý do: lúc đầu `a` và `b` trỏ cùng một đối tượng; `b.name` thay đổi đối tượng đó. Sau `a = c`, biến `a` chuyển sang cùng đối tượng với `c`, còn `b` tiếp tục trỏ đối tượng ban đầu. Đoạn này là phần thân phương thức minh họa, có thể đặt trong `main` của một lớp chạy thử nếu đã khai báo `Person`.

Khi đọc bất kỳ dòng Java nào có một tên lớp và dấu `=`, hãy tự hỏi: **(1)** kiểu nào đang được khai báo? **(2)** biến nào giữ tham chiếu? **(3)** có thực sự gọi `new` để tạo đối tượng không? **(4)** các biến nào đang tham chiếu cùng một đối tượng? Bốn câu hỏi đó đủ để phân biệt chính xác khai báo lớp, biến tham chiếu và thể hiện trong hầu hết tình huống Java cơ bản.
