# Lộ trình học và kiến thức Java nền tảng cần có trước khi học Class & Object

Trong Java, **class** mô tả cấu trúc và hành vi của một loại đối tượng; **object** là một thể hiện cụ thể được tạo và sử dụng khi chương trình chạy. Để học phần **Java Core – Class & Object** hiệu quả, người học cần nối được kiến thức cú pháp Java với cách đối tượng được khởi tạo, lưu trạng thái, nhận lời gọi phương thức và cộng tác với những đối tượng khác.

Bài này là **bản đồ học tập và danh sách năng lực đầu vào**, giúp trả lời ba câu hỏi:

1. Cần biết những gì để bắt đầu?
2. Nên học kiến thức class/object theo thứ tự nào để các khái niệm không bị rời rạc?
3. Dựa vào đâu để xác nhận rằng mình đã hiểu và tự viết được chương trình sử dụng đối tượng?

Bạn không cần học xong toàn bộ Java hay các framework rồi mới học class/object. Chỉ cần nắm chắc cú pháp cơ bản, biến và kiểu dữ liệu, điều kiện, vòng lặp, phương thức, và phân biệt sơ bộ giá trị nguyên thủy với tham chiếu. Những chủ đề nâng cao như reflection, generics chuyên sâu, đa luồng, Spring hay cơ chế class loading có thể học sau.

## 1. Bức tranh tổng thể: điều gì phụ thuộc vào điều gì?

~~~text
JDK, javac, java, cấu trúc tệp nguồn
                  |
Kiểu dữ liệu, biến, biểu thức, toán tử
                  |
Điều kiện, vòng lặp, mảng; phương thức
                  |
Phân biệt primitive và reference, null
                  |
       class và object, new
                  |
Trường (field), phương thức (method), this
                  |
Constructor, khởi tạo và trạng thái hợp lệ
                  |
instance / static, phạm vi và vòng đời dữ liệu
                  |
Đóng gói, access modifier, kiểm tra invariant
                  |
Object identity, alias, == và equals
                  |
Hai hay nhiều object cộng tác; bài tập tổng hợp
~~~

Sơ đồ diễn tả **thứ tự khuyến nghị**, không phải thứ tự cứng của tất cả chương trình học. Ví dụ, có thể gặp `String` (một class) từ rất sớm dù chưa học lý thuyết về object; lúc đó chỉ cần biết dùng chuỗi, sau này mới đào sâu vì sao `String` là reference type.

| Chặng | Kiến thức chính | Sản phẩm/năng lực kiểm tra |
| --- | --- | --- |
| 0. Môi trường Java | JDK, terminal, `javac`, `java`, tệp `.java` | Tự biên dịch và chạy một chương trình |
| 1. Cú pháp và dữ liệu | Biến, primitive, `String`, `null`, toán tử, ép kiểu | Dự đoán giá trị biểu thức, tránh so sánh sai kiểu |
| 2. Luồng điều khiển và phương thức | `if`, `switch`, vòng lặp, mảng, parameter, return | Tách thuật toán thành phương thức nhỏ |
| 3. Mô hình đối tượng | `class`, `new`, field, method, `this` | Tạo hai object và chứng minh state độc lập |
| 4. Khởi tạo và phân quyền | Constructor, `static`/instance, `private`/`public`, getter, hành vi cập nhật | Ngăn tạo hoặc đưa object vào trạng thái sai |
| 5. Tham chiếu và so sánh | Alias, truyền tham số, `==`, `equals`, `final`, null | Giải thích được vì sao hai biến cùng thấy một thay đổi |
| 6. Vận dụng | Nhiều object tương tác, xử lý dữ liệu và kiểm thử đơn giản | Hoàn thành bài quản lý đối tượng với ca hợp lệ và bất hợp lệ |

## 2. Chặng 0 — Biết công cụ đang chạy chương trình Java như thế nào

### JDK, JVM và quy trình từ mã nguồn đến chương trình

- **JDK (Java Development Kit)** chứa công cụ phát triển cần thiết, trong đó có trình biên dịch `javac` và công cụ chạy `java`.
- **JVM (Java Virtual Machine)** thực thi mã bytecode Java. Trình biên dịch Java thông thường dịch mã nguồn `.java` thành bytecode trong `.class`.
- **`javac`** dùng để biên dịch; **`java`** thường dùng để khởi chạy chương trình có entry point phù hợp. Đối với bài học này, dùng JDK 17 trở lên.

Kiểm tra terminal:

~~~bash
java -version
javac -version
~~~

Hai lệnh cần chạy được. Phiên bản cụ thể và chuỗi thông báo phụ thuộc JDK đã cài.

Tạo tệp **`HelloJava.java`**:

~~~java
public class HelloJava {
    public static void main(String[] args) {
        System.out.println("Hello, Java!");
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac HelloJava.java
java HelloJava
~~~

Stdout:

~~~text
Hello, Java!
~~~

Những chi tiết ban đầu phải nhận diện được:

- Tên tệp `HelloJava.java` khớp với tên `public class HelloJava`.
- Khối mã nằm trong các cặp ngoặc nhọn `{ }`; câu lệnh gọi `println` kết thúc bằng dấu chấm phẩy.
- `public static void main(String[] args)` là điểm vào thông dụng cho chương trình console Java. `static` cho phép chạy `main` mà chưa phải tự tạo instance của `HelloJava`.
- `System.out.println(...)` in chuỗi ra luồng đầu ra chuẩn và xuống dòng.
- Với tệp nguồn chứa nhiều class cấp cao nhất, tối đa một class có thể là `public`; tên file phải trùng tên class public đó.
- Tên class theo quy ước `UpperCamelCase`; method và biến theo `lowerCamelCase`. Quy ước tên giúp code dễ đọc nhưng không phải tất cả đều là quy tắc bắt buộc của trình biên dịch.

**Điểm kiểm tra:** Bạn có thể tạo file mới, biên dịch, sửa một lỗi cú pháp cố ý, đọc thông báo lỗi, rồi chạy lại. Nếu chưa làm được, hãy thành thạo trước khi chuyển sang các ví dụ nhiều class.

## 3. Chặng 1 — Biến, kiểu dữ liệu và biểu thức

### Primitive và reference: kiến thức đầu vào quan trọng nhất

Java phân biệt **kiểu nguyên thủy (primitive)** và **kiểu tham chiếu (reference)**.

| Primitive | Ví dụ | Ghi nhớ |
| --- | --- | --- |
| Số nguyên | `byte`, `short`, `int`, `long` | Chứa giá trị số nguyên trong miền biểu diễn của kiểu |
| Số thực | `float`, `double` | Xấp xỉ nhị phân; không đại diện chính xác mọi số thập phân |
| Ký tự | `char` | Một đơn vị mã UTF-16, không đồng nghĩa một ký tự Unicode hoàn chỉnh |
| Logic | `boolean` | `true` hoặc `false` |

Các kiểu như `String`, mảng `int[]`, và class do bạn viết là **reference type**. Biến reference chứa một giá trị tham chiếu đến object hoặc `null`; gán tham chiếu vào biến khác không tự tạo thêm object.

Ví dụ biểu thức:

~~~java
int quantity = 3;
double unitPrice = 19.5;
double total = quantity * unitPrice;
String label = "Sách";
boolean available = quantity > 0;
~~~

`quantity`, `unitPrice`, `total` và `available` có kiểu primitive; `label` có kiểu `String`, là object bất biến theo giá trị chuỗi. Không suy luận rằng kiểu nào viết ngắn hay dùng dấu ngoặc kép sẽ trở thành primitive.

### Cần nắm trước khi viết class

1. **Khai báo và gán:** `int age = 18;`, đọc lại giá trị, thay đổi bằng phép gán `age = 19;`.
2. **Phạm vi biến:** biến cục bộ của phương thức chỉ có phạm vi tương ứng; trường của object có phạm vi và vòng đời khác.
3. **Toán tử:** `+`, `-`, `*`, `/`, `%`, `==`, `!=`, `>`, `>=`, `&&`, `||`, `!`.
4. **Ép kiểu:** `(double) total / count` khác với thực hiện phép chia nguyên trước rồi mới ép kiểu.
5. **Chuỗi:** nối chuỗi bằng `+`; so sánh nội dung bằng `equals`; lưu ý `null` không phải chuỗi rỗng `""`.
6. **Literal:** phân biệt `5` (`int`), `5L` (`long`), `5.0` (`double`), `'A'` (`char`), `"A"` (`String`).
7. **`final`:** biến cục bộ `final int limit = 10;` không thể được gán lần nữa. Với biến tham chiếu `final`, không được gán sang tham chiếu khác; object đang trỏ đến vẫn có thể mutable.

Lưu ý phép chia số nguyên: `7 / 2` cho `3`, trong khi `7.0 / 2` cho `3.5`. Điều này rất dễ làm sai kết quả nếu một field được tính từ các số nguyên.

### Phân biệt giá trị mặc định của field với biến cục bộ

Các **instance field** có giá trị mặc định khi object được cấp phát trước khi các bước khởi tạo cụ thể diễn ra: `int` mặc định `0`, `boolean` mặc định `false`, reference mặc định `null`. **Biến cục bộ** không được phép đọc trước khi compiler xác định đã được gán giá trị.

~~~java
class Example {
    int count;              // Mặc định 0 khi instance được khởi tạo
    String description;     // Mặc định null
    void work() {
        int localCount = 0; // Phải khởi tạo trước khi đọc
        System.out.println(localCount);
    }
}
~~~

Giá trị mặc định chỉ là cơ chế khởi tạo của Java; không bảo đảm chúng hợp lệ về nghiệp vụ. Chẳng hạn trường `email` mặc định `null` có thể không đáp ứng điều kiện của ứng dụng.

## 4. Chặng 2 — Điều kiện, vòng lặp, mảng và phương thức

Các phương thức của object dùng cùng những cấu trúc điều khiển như chương trình Java cơ bản. Bạn cần tự đọc và viết được:

- `if / else` để rẽ nhánh theo điều kiện;
- `switch` ở mức cơ bản nếu bài toán có nhiều trường hợp;
- `for`, enhanced `for` và `while` để lặp;
- mảng `int[]` cùng `length` và chỉ số bắt đầu từ `0`;
- `break`, `continue` khi có lý do rõ ràng;
- phương thức có tham số, kiểu trả về, `return` và `void`.

Một chương trình kiểm tra tổng hợp, lưu thành **`BasicsCheckpoint.java`**:

~~~java
public class BasicsCheckpoint {

    static int sumPositive(int[] numbers) {
        int sum = 0;

        for (int value : numbers) {
            if (value <= 0) {
                continue;
            }
            sum += value;
        }

        return sum;
    }

    static int countPositive(int[] numbers) {
        int count = 0;

        for (int value : numbers) {
            if (value > 0) {
                count++;
            }
        }

        return count;
    }

    public static void main(String[] args) {
        int[] scores = {3, 0, 5, -1};

        int sum = sumPositive(scores);
        int count = countPositive(scores);
        double average = count == 0 ? 0.0 : (double) sum / count;

        System.out.println("Số phần tử dương: " + count);
        System.out.println("Tổng: " + sum);
        System.out.println("Trung bình: " + average);
    }
}
~~~

~~~bash
javac -encoding UTF-8 BasicsCheckpoint.java
java BasicsCheckpoint
~~~

Stdout:

~~~text
Số phần tử dương: 2
Tổng: 8
Trung bình: 4.0
~~~

Giải thích: `sumPositive` và `countPositive` nhận tham số `int[]`, lần lượt tính tổng và đếm các phần tử lớn hơn `0`. `(double) sum / count` giúp phép chia cho ra kết quả số thực. Trước khi học object, hãy thử thay mảng bằng `{0, -2}` và giải thích vì sao phải kiểm tra `count == 0` trước phép chia. Ví dụ có `0.0` để đại diện trường hợp không có phần tử dương theo quy tắc bài tập; một ứng dụng thật có thể chọn trả thông tin “không có dữ liệu” thay vì `0.0`.

### Phương thức là viên gạch để xây dựng hành vi object

Một khai báo method có kiểu trả về, tên, danh sách tham số và thân hàm:

~~~java
static int twice(int value) {
    return value * 2;
}
~~~

`static` trong ví dụ cho phép gọi trực tiếp từ `main`. Sau khi học class/object, bạn sẽ viết **instance method** như `wallet.deposit(amount)`; khác biệt chính là instance method gắn với một object cụ thể và có thể truy cập trạng thái instance thông qua `this`.

**Điểm kiểm tra:** Bạn hiểu tham số dùng để nhận dữ liệu, `return` trả kết quả, và biết giải thích mỗi nhánh điều kiện. Nếu một method làm quá nhiều việc, hãy thử tách nó thành hai method rõ nhiệm vụ.

## 5. Chặng 3 — Chuyển từ lập trình theo biến rời rạc sang class và object

Khi xử lý một thực thể có nhiều dữ liệu liên quan, dùng các biến riêng lẻ dễ khiến thông tin tách rời nhau:

~~~java
String learnerName = "Mai";
int pagesRead = 12;
~~~

Đây là cách hợp lệ cho ví dụ rất nhỏ. Khi ứng dụng cần quản lý nhiều người đọc, ta muốn gom dữ liệu gắn liền và hành vi điều khiển nó vào class:

~~~java
class ReadingList {
    String owner;
    int pagesRead;

    void recordPages(int pages) {
        pagesRead += pages;
    }
}
~~~

Đoạn trên chỉ là **mã minh họa class**, chưa phải ứng dụng console chạy độc lập. Nó giúp xác định:

- **`class`:** bản mô tả chung về trường và method.
- **Instance/object:** thực thể riêng được tạo bằng `new ReadingList()`.
- **Field:** `owner` và `pagesRead` lưu state của từng instance.
- **Instance method:** `recordPages` thể hiện hành vi gắn với instance.
- **`this`:** bên trong instance method, `this` tham chiếu đến object đang nhận lời gọi.
- **Dấu chấm `.`:** `list.recordPages(5)` truy cập hành vi; `list.pagesRead` truy cập field nếu Java access rule cho phép.

Cần phân biệt “class là bản thiết kế” chỉ là cách ví von để nhập môn. Class thực tế còn định nghĩa phạm vi truy cập, constructor, thông tin kiểu và các quy tắc trong ngôn ngữ; còn object không chỉ là bản sao của các dòng khai báo.

## 6. Chặng 4 — Constructor, instance/static và đóng gói

### Constructor thiết lập trạng thái ban đầu

Constructor có **tên trùng với class** và **không khai báo kiểu trả về**, kể cả `void`. Nó được gọi trong quá trình khởi tạo bằng `new`. Ví dụ:

~~~java
class ReadingList {
    private final String owner;
    private int pagesRead;

    ReadingList(String owner) {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("owner is required");
        }
        this.owner = owner;
        this.pagesRead = 0;
    }

    void recordPages(int pages) {
        if (pages <= 0) {
            throw new IllegalArgumentException("pages must be positive");
        }
        pagesRead += pages;
    }

    int getPagesRead() {
        return pagesRead;
    }
}
~~~

Đây là một **định nghĩa class minh họa**, sẽ được đưa vào chương trình chạy đầy đủ ở phần sau.

Các ý quan trọng:

- `ReadingList(String owner)` là constructor có một tham số. Do đã khai báo constructor này, class không tự có thêm constructor không tham số mặc định.
- `this.owner = owner` phân biệt trường của instance (`this.owner`) với tham số cùng tên (`owner`).
- `private` ngăn mã bên ngoài class truy cập trực tiếp trường; nó vẫn cho phép phương thức nội bộ đọc và chỉnh sửa.
- `final` trên trường `owner` yêu cầu gán đúng theo quy tắc khởi tạo Java và không cho gán lại về sau bằng mã Java thông thường.
- `recordPages` kiểm tra `pages > 0`; số trang đã đọc không được giảm do đầu vào âm.
- `getPagesRead` chỉ đọc field; không phải mọi field đều phải có cả getter và setter.
- Nếu lập trình viên muốn một object luôn bắt đầu hợp lệ, constructor là một nơi quan trọng để kiểm tra đầu vào.

Một cách phân biệt ngắn gọn:

| Thành phần | Thuộc instance hay class? | Ví dụ |
| --- | --- | --- |
| Instance field | Riêng từng object | `pagesRead` của từng ReadingList |
| Instance method | Gọi trên một object | `list.recordPages(5)` |
| `static` field | Một field ở cấp class, được các instance cùng tham chiếu theo ngữ nghĩa Java | `ReadingList.createdCount` |
| `static` method | Gọi với tên class, không có `this` | `ReadingList.totalCreated()` |
| Constructor | Được thực thi khi tạo instance mới | `new ReadingList("Mai")` |

Đừng dùng `static` cho dữ liệu riêng của mỗi đối tượng. Nếu đặt `pagesRead` thành static, các instance có thể cùng thấy một giá trị chung, trái với mô hình nhiều danh sách đọc độc lập.

### Đóng gói bảo vệ invariant

**Encapsulation (đóng gói)** là quản lý truy cập vào dữ liệu và đặt thao tác hợp lệ bên cạnh dữ liệu đó. Một **invariant** là điều kiện cần được duy trì trong các trạng thái hợp lệ, ví dụ `pagesRead >= 0`.

Không nên cung cấp một setter bất kỳ như `setPagesRead(-999)` nếu thiết kế không cho phép số âm. Thay vào đó cung cấp hành vi có ý nghĩa nghiệp vụ `recordPages(pages)` và kiểm tra tham số. Thiết kế này giúp giảm số chỗ có thể làm state sai.

Các access modifier thường gặp:

| Modifier | Phạm vi truy cập cơ bản |
| --- | --- |
| `public` | Các mã có quyền truy cập đến kiểu/thành viên theo quy tắc Java (bao gồm hệ thống module nếu áp dụng) |
| `protected` | Cùng package và truy cập thích hợp từ subclass ở package khác |
| *Không ghi modifier* (package-private) | Trong cùng package |
| `private` | Bên trong phạm vi class/nest tương ứng theo quy tắc ngôn ngữ |

Ở mức nhập môn, hãy bắt đầu từ `private` field và `public` method khi API thực sự cần công khai. Về sau mới đào sâu kế thừa và các quy tắc truy cập phức tạp.

## 7. Chặng 5 — Kiểm tra tham chiếu, danh tính object, null và truyền tham số

Ở chặng này, trọng tâm của **lộ trình học** là tự xác định mình đã đọc được object graph, thay vì học lại toàn bộ định nghĩa của `class` và `new`. Trước khi chuyển sang bài tích hợp ở chặng 6, hãy dùng chính lớp `ReadingList` ở chặng trước để hoàn thành những phép thử sau.

| Phép thử đầu ra | Bạn phải giải thích được |
| --- | --- |
| `ReadingList a = new ReadingList("Mai"); ReadingList b = a;` | Hai biến giữ cùng reference; không gọi constructor lần hai |
| `ReadingList c = new ReadingList("Mai");` | Tên người đọc trùng nhau không có nghĩa cùng instance |
| `b.recordPages(5)`, rồi đọc `a.getPagesRead()` | State thay đổi qua b được a quan sát vì alias |
| `a == b` và `a == c` | `==` với references so danh tính object, không so nội dung |
| `b = c;`, rồi đọc qua `a` | Gán lại biến b không hoàn tác state của object a |
| `ReadingList missing = null;` | Không có object để gọi instance method; phải xử lý null trước khi truy cập |
| `final ReadingList fixed = a;` | Biến fixed không được gán lại; referenced object vẫn có thể mutable |

**Bài kiểm tra pass-by-value:** tự viết method `static void update(ReadingList value)` gọi `value.recordPages(2)`, sau đó gán `value = new ReadingList("Khác")`. Khi gọi bằng `a`, object cũ được tăng hai trang nhưng biến a của caller **không** bị thay sang object mới. Java sao chép **giá trị tham chiếu** vào parameter.

**Bài kiểm tra equality:** so `String.equals` để kiểm tra nội dung chuỗi, so references với `==` nếu cần biết có **cùng instance** không. `Object.equals` mặc định so danh tính, còn lớp/record có thể quy định giá trị bằng nhau khác. Để thấy rõ không phải lúc nào `==` đều cho quan hệ giá trị mong muốn, thử hai `new String("Java")` riêng rồi so `==` và `equals`. Đây là thí nghiệm về reference equality, không khuyến nghị dùng `new String` trong mã nghiệp vụ thông thường.

**Tiêu chí đạt:** không cần thuộc lòng định nghĩa dài; bạn phải vẽ được mũi tên giữa ba biến và hai objects, đếm đúng số constructor calls, dự đoán thay đổi state, phân biệt null với object và giải thích việc reassign parameter không đổi biến ở caller. Nếu một phép thử chưa chắc, chạy ví dụ tối thiểu rồi đối chiếu; khi đã thành thạo, sang chặng 6.

## 8. Chặng 6 — Chương trình hoàn chỉnh kết hợp các kiến thức

Ví dụ này gom các mục tiêu của lộ trình: class, hai instance, constructor, field `private`, kiểm tra đầu vào, instance method, static method, alias và so sánh tham chiếu.

Tạo **`ClassObjectRoadmapDemo.java`**:

~~~java
public class ClassObjectRoadmapDemo {

    static final class ReadingList {
        private static int createdCount;

        private final String owner;
        private int pagesRead;

        ReadingList(String owner) {
            if (owner == null || owner.isBlank()) {
                throw new IllegalArgumentException("owner is required");
            }
            this.owner = owner;
            this.pagesRead = 0;
            createdCount++;
        }

        void recordPages(int pages) {
            if (pages <= 0) {
                throw new IllegalArgumentException("pages must be positive");
            }
            pagesRead = Math.addExact(pagesRead, pages);
        }

        int getPagesRead() {
            return pagesRead;
        }

        String summary() {
            return owner + ": " + pagesRead + " pages";
        }

        static int totalCreated() {
            return createdCount;
        }
    }

    public static void main(String[] args) {
        ReadingList mai = new ReadingList("Mai");
        ReadingList alias = mai;
        ReadingList nam = new ReadingList("Nam");

        mai.recordPages(12);
        alias.recordPages(5);
        nam.recordPages(9);

        System.out.println(mai.summary());
        System.out.println(nam.summary());
        System.out.println("Cùng instance: " + (mai == alias));
        System.out.println("Khác instance: " + (mai == nam));
        System.out.println("Số đối tượng đã tạo: " + ReadingList.totalCreated());
    }
}
~~~

Trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ClassObjectRoadmapDemo.java
java ClassObjectRoadmapDemo
~~~

Stdout:

~~~text
Mai: 17 pages
Nam: 9 pages
Cùng instance: true
Khác instance: false
Số đối tượng đã tạo: 2
~~~

### Từng dòng liên hệ với kiến thức nào?

1. `static final class ReadingList` là một nested class được khai báo bên trong class chứa `main`. Nested class này là static nên không cần một instance của class bao ngoài. Việc dùng nested class ở đây giúp ví dụ chạy trong **một tệp duy nhất**; bạn cũng có thể dùng hai class cấp cao nhất đặt đúng cách trong các tệp nguồn.
2. `owner` và `pagesRead` là instance field. Mỗi ReadingList giữ dữ liệu riêng, vì vậy Mai đọc 17 trang và Nam đọc 9 trang.
3. `createdCount` là static field. Cả hai lần gọi constructor đều tăng chung một biến đếm. Ví dụ chạy tuần tự; phép tăng đếm này không được thiết kế cho truy cập đồng thời.
4. Constructor kiểm tra tên, gán trường `final` và thiết lập `pagesRead = 0`. Nếu tên null hoặc toàn khoảng trắng, `IllegalArgumentException` được ném trước khi đếm object hợp lệ.
5. `recordPages` thể hiện hành vi: chỉ nhận số trang dương. `Math.addExact` phát hiện tràn số `int` bằng cách ném `ArithmeticException` thay vì âm thầm ghi kết quả tràn.
6. `alias = mai` chỉ sao chép tham chiếu, do đó `mai.recordPages(12)` và `alias.recordPages(5)` cập nhật cùng ReadingList.
7. `nam = new ReadingList("Nam")` tạo instance riêng. Nó không bị ảnh hưởng bởi thao tác qua `mai` và `alias`.
8. `mai == alias` là `true`; `mai == nam` là `false`. Các giá trị đó phản ánh danh tính object chứ không phản ánh tên hoặc số trang.
9. `ReadingList.totalCreated()` là gọi static method trên tên class để đọc dữ liệu chung.

**Tự thử có chủ đích:** thay `alias.recordPages(5)` bằng `alias.recordPages(-5)` và giải thích vì sao chương trình dừng bằng exception; thử thay tên `"Mai"` bằng `""`; thử đổi `alias` để tham chiếu sang `nam` trước khi ghi trang. Mỗi thay đổi làm rõ một quy tắc cụ thể.

## 9. Bài tập thực hành theo cấp độ và tiêu chí đạt

Đừng chỉ đọc mã rồi cảm thấy quen. Hãy **tự gõ lại từ đầu**, chạy thử rồi lý giải output và nguyên nhân xảy ra lỗi.

### Mức 1 — Cú pháp và phương thức

**Bài tập:** Viết `calculateTotal(int price, int quantity)` trả tổng tiền. Nếu tham số âm, ném `IllegalArgumentException`.

**Đạt khi:** chạy được với `price = 25`, `quantity = 3` cho `75`; phân biệt được tham số đầu vào, biến cục bộ và giá trị trả về; giải thích vì sao kiểm tra đầu vào trước khi tính. Có thể dùng `Math.multiplyExact` nếu muốn phát hiện tràn số.

### Mức 2 — Hai object độc lập

**Bài tập:** Tạo class `Counter` có trường `private int value`, constructor nhận số ban đầu, method `increment()`, method `getValue()`.

**Kịch bản:** Tạo `Counter left = new Counter(1)` và `Counter right = new Counter(1)`, tăng `left` hai lần. Kết quả phải là `left = 3`, `right = 1`.

**Đạt khi:** giải thích được vì sao hai object có thể có giá trị ban đầu giống nhau nhưng state không liên thông. Nếu đặt `value` thành `static`, bạn giải thích được vì sao thiết kế không đúng bài toán.

### Mức 3 — Kiểm tra trạng thái hợp lệ

**Bài tập:** Viết `BankAccount` có `private long balance`, constructor yêu cầu số dư không âm, `deposit(long amount)` chỉ nhận số dương và `withdraw(long amount)` từ chối rút vượt số dư.

**Đạt khi:** tạo object hợp lệ, cập nhật đúng trạng thái sau ba thao tác; kiểm tra những trường hợp tiền âm, bằng 0, rút quá số dư. Không có đường gọi API công khai nào cho phép giữ số dư âm.

### Mức 4 — Tham chiếu và alias

**Bài tập:** Tạo một `Counter a`, sau đó `Counter b = a`; tăng qua `b` và đọc qua `a`. Tiếp theo tạo `Counter c = new Counter(...)` với số ban đầu trùng với `a`.

**Đạt khi:** đoán đúng `a == b` và `a == c`; biết `b = c` không sửa biến `a` hay hoàn tác lần tăng trước.

### Mức 5 — Hai loại đối tượng cộng tác

**Bài tập:** Viết class `Book` giữ `title` và số trang hợp lệ; class `ReadingProgress` giữ một tham chiếu đến `Book` và số trang đã đọc. Hành vi `read(int pages)` không cho số trang đã đọc vượt tổng số trang sách.

**Đạt khi:** mỗi class có trách nhiệm rõ; constructor kiểm tra điều kiện; tạo hai tiến độ đọc cho cùng một `Book` và chỉ ra tiến độ nào là độc lập, object nào đang được chia sẻ. Hãy cân nhắc việc chia sẻ một `Book` mutable có thể ảnh hưởng đến bất biến của `ReadingProgress` như thế nào.

### Mức 6 — Tự kiểm thử chương trình nhỏ

Dùng `if` và ném `AssertionError` để xác nhận kết quả, chẳng hạn đặt trong `main`:

~~~java
if (mai.getPagesRead() != 17) {
    throw new AssertionError("Expected Mai to read 17 pages");
}
~~~

Đây là kiểm tra cơ bản không cần thư viện bổ sung. Khi học quy mô lớn hơn, có thể chuyển sang JUnit để quản lý nhiều test case. Đạt khi bạn tự nghĩ được ít nhất một ca bình thường, một ca biên và một ca đầu vào không hợp lệ cho mỗi hành vi cập nhật.

## 10. Checklist trước khi chuyển sang phần kiến thức Class & Object sâu hơn

Dùng các câu sau như tiêu chí đầu ra. Chỉ cần tiếp tục luyện đúng chỗ chưa chắc; không cần đợi “học hết Java”.

| Câu hỏi tự đánh giá | Biểu hiện đã nắm |
| --- | --- |
| Tôi có thể tự chạy file `.java` không? | Tạo file, `javac`, `java` và hiểu lỗi tên class/tên file |
| Tôi phân biệt primitive và reference không? | Giải thích được `int x = 2` khác `Counter c = new Counter(2)` |
| Tôi đọc được `if`, vòng lặp và method không? | Dự đoán output, hiểu parameter và `return` |
| Tôi biết class và instance khác nhau thế nào không? | Tạo hai object, mỗi object giữ state riêng |
| Tôi dùng constructor và `this` được không? | Khởi tạo đúng, giải thích `this.field = parameter` |
| Tôi biết instance field so với static field không? | Chọn đúng nơi chứa dữ liệu riêng hoặc chung |
| Tôi biết bảo vệ state không? | Field `private`, hành vi kiểm tra đầu vào, giữ invariant |
| Tôi biết alias không? | Giải thích vì sao hai biến có thể trỏ cùng object |
| Tôi phân biệt `==` và `equals` không? | Biết so sánh reference identity và value equality theo class |
| Tôi xử lý `null` cơ bản không? | Tránh gọi method trên null; kiểm tra tại ranh giới đầu vào |
| Tôi biết `final` giới hạn điều gì không? | Không nhầm biến final với object immutable |
| Tôi tự kiểm tra code không? | Có ca hợp lệ, biên và sai; kiểm tra giá trị sau thao tác |

Nếu các mục đều làm được với chương trình tự viết, bạn đã có nền tảng vững để chuyển sang những bài chi tiết hơn về vòng đời object, constructor overload, khai báo class, mức truy cập, quan hệ giữa object và các quy tắc so sánh.

## 11. Lỗi phổ biến và cách tự chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `class HelloJava is public, should be declared in a file named HelloJava.java` | Tên file không trùng tên public class | Sửa đúng cặp tên file/class, phân biệt hoa-thường |
| `cannot find symbol` | Sai tên, sai phạm vi, chưa khai báo, hoặc class chưa có trên đường dẫn biên dịch | Đọc tên symbol báo lỗi, kiểm tra cú pháp và file nguồn |
| `non-static variable ... cannot be referenced from a static context` | Đang dùng field/method instance trực tiếp từ static method | Tạo instance rồi truy cập qua biến tham chiếu, hoặc xem lại thiết kế static |
| `variable ... might not have been initialized` | Đọc biến cục bộ trước khi compiler xác nhận đã gán | Khởi tạo hoặc đảm bảo mọi nhánh trước lần đọc đều gán |
| `NullPointerException` | Gọi method hoặc dùng dữ liệu từ tham chiếu null | Xem điểm tạo dữ liệu, validate đầu vào và vòng đời tham chiếu |
| Hai biến đổi theo nhau ngoài dự tính | Hai biến có thể đang trỏ cùng object mutable | Kiểm tra phép gán tham chiếu và những method cập nhật state |
| Hai object dữ liệu giống nhau nhưng `==` là false | `==` trên reference so sánh danh tính | Chọn định nghĩa `equals` hoặc so sánh dữ liệu nghiệp vụ khi phù hợp |
| Lỗi khi gọi `new Class()` | Class chỉ có constructor nhận tham số hoặc constructor không thể truy cập | Kiểm tra chữ ký constructor, modifier và cách khởi tạo |
| Setter cho phép object vào trạng thái sai | Không kiểm tra bất biến ở constructor/method | Giới hạn đường cập nhật, validate tham số và kết quả |
| “Không chạy được `main`” | Đang chạy tên file thay vì tên class theo quy trình đã chọn, hoặc thiếu entry point phù hợp | Xác nhận `public static void main(String[] args)` và lệnh chạy |

Từ Java 11 trở lên, công cụ `java` còn hỗ trợ chạy trực tiếp một tệp mã nguồn trong một số tình huống (`java HelloJava.java`). Dù vậy, khi đang học nền tảng, tách riêng `javac` và `java` giúp hiểu rõ đâu là lỗi biên dịch và đâu là lỗi lúc thực thi.

## 12. Nội dung nên học tiếp và nội dung có thể để sau

**Ngay sau bài lộ trình này**, nên đào sâu từng chủ điểm class/object: cấu trúc class; constructor và overload; instance field/method; `this`; truy cập và đóng gói; quan hệ tham chiếu; state, behavior, identity; phương thức của `Object`; so sánh giá trị; thiết kế object có trạng thái hợp lệ. Các mục có liên hệ với nhau: mỗi lần gặp khái niệm mới, hãy quay về class nhỏ mình đã tự viết để chỉnh sửa và quan sát hành vi.

**Sau khi dùng class/object thành thạo**, mới cần dành một chặng riêng cho kế thừa và đa hình, interface và abstract class, exception nâng cao, collections/generics, lambda, test framework, concurrency, Java modules hoặc Spring. Các nội dung ấy xây dựng trên hiểu biết về instance, reference và method; học vội khi chưa làm rõ các nền tảng thường dẫn đến code hoạt động tình cờ nhưng khó giải thích.

### Cách học để giữ kiến thức lâu

1. **Đọc một khái niệm → chạy ví dụ tối thiểu → tự sửa một tình huống:** ví dụ sau `new` hãy thêm object thứ hai; sau constructor hãy thử giá trị đầu vào bất hợp lệ.
2. **Dự đoán trước khi chạy:** ghi ra stdout dự kiến, sau đó kiểm tra bằng compiler và runtime. Nếu sai, giải thích nguyên nhân bằng khái niệm về state, reference hoặc phạm vi.
3. **Vẽ quan hệ tham chiếu:** với `a`, `b`, `c`, vẽ mũi tên vào object để hiểu alias và independent instance.
4. **Đặt câu hỏi theo ba lớp:** dữ liệu này thuộc class hay instance? Method này tác động state nào? Hai biến là cùng object hay chỉ có giá trị bằng nhau?
5. **Tập diễn đạt bằng lời của mình:** nếu có thể giải thích vì sao `alias.recordPages(5)` làm thay đổi kết quả khi đọc qua `mai`, kiến thức sẽ hữu ích hơn việc nhớ định nghĩa.

**Kết quả mong đợi:** Bạn không chỉ thuộc cú pháp `class` và `new`, mà còn biết tạo object với state hợp lệ, thiết kế hành vi rõ ràng, chọn instance/static đúng chỗ, phân biệt giá trị và tham chiếu, dự đoán tác động của các method, và tự chạy/kiểm chứng chương trình Java 17+ dùng nhiều object.
