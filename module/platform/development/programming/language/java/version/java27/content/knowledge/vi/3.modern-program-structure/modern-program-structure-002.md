# Compact source files và instance main methods cho chương trình nhỏ

Trong Java, một chương trình nhỏ thường chỉ cần vài biến, một số phương thức và một điểm bắt đầu để chạy. Trước Java 25, ngay cả ví dụ chỉ in một dòng chữ cũng thường phải khai báo một lớp, viết **public static void main(String[] args)** và dùng **System.out.println**. Những khai báo đó có ích khi tổ chức phần mềm lớn, nhưng có thể khiến người mới học phải tiếp cận nhiều khái niệm cùng lúc.

Java 25 chuẩn hóa **Compact Source Files và Instance Main Methods** qua JEP 512. Java 27 tiếp tục hỗ trợ tính năng này như một phần chính thức của ngôn ngữ. Nhờ đó, chương trình một tệp có thể tập trung vào logic cần học; khi chương trình lớn dần, ta vẫn có thể chuyển sang lớp, package và module thông thường.

Bài viết sử dụng cú pháp Java 27 hiện hành. Các ví dụ không yêu cầu bật preview feature.

## 1. Mục tiêu và phạm vi sử dụng

Sau bài học, bạn có thể:

- Giải thích compact source file và lớp được khai báo ngầm.
- Viết chương trình Java nhỏ mà không cần khai báo lớp tường minh.
- Sử dụng instance **main** không có **static**, không bắt buộc **public** và có thể không nhận **String[]**.
- Hiểu cách Java Launcher tìm và gọi phương thức **main**.
- Dùng các kiểu trong module **java.base** và lớp **java.lang.IO** trong compact source file.
- Chạy trực tiếp tệp **.java**, hoặc biên dịch rồi chạy chương trình.
- Nhận biết khi nào nên chuyển sang lớp và cấu trúc package thông thường.

Tính năng này phù hợp với bài tập, ví dụ giảng dạy, chương trình thử nghiệm và tiện ích một tệp. Nó không loại bỏ mô hình lớp của Java, cũng không thay thế cách tổ chức ứng dụng nhiều lớp, nhiều package hoặc nhiều module.

## 2. Từ chương trình truyền thống đến compact source file

Một chương trình Hello World theo cách viết quen thuộc:

~~~java
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}
~~~

Để hiểu ví dụ này, người mới học phải làm quen ngay với nhiều thành phần:

- **class HelloWorld**: khai báo một lớp.
- **public**: chỉ định mức truy cập.
- **static**: phương thức thuộc về lớp, không cần tạo đối tượng để gọi.
- **void**: phương thức không trả về giá trị.
- **String[] args**: mảng chứa đối số dòng lệnh.
- **System.out.println(...)**: gọi phương thức in ra đầu ra chuẩn.

Các thành phần trên vẫn cần thiết trong nhiều chương trình thực tế. Tuy nhiên, một bài tập đầu tiên chỉ cần in thông báo không nhất thiết phải giới thiệu tất cả chúng cùng lúc.

Với compact source file, có thể viết:

~~~java
void main() {
    IO.println("Hello, World!");
}
~~~

Lưu đoạn mã vào tệp **HelloWorld.java**, sau đó chạy:

~~~bash
java HelloWorld.java
~~~

Kết quả:

~~~text
Hello, World!
~~~

Đoạn mã vẫn là Java thông thường: được kiểm tra cú pháp, kiểm tra kiểu và thực thi trên JVM. Điểm khác biệt nằm ở cách khai báo chương trình. Trình biên dịch hiểu các thành viên được khai báo bên ngoài một lớp tường minh là thành viên của một lớp được khai báo ngầm.

## 3. Compact source file và lớp được khai báo ngầm

**Compact source file** là tệp nguồn Java khai báo thành viên lớp trực tiếp, không đặt chúng bên trong một khai báo lớp tường minh ở cấp cao nhất.

Ví dụ:

~~~java
String applicationName = "Theo dõi chi tiêu";

int total(int... amounts) {
    int sum = 0;

    for (int amount : amounts) {
        sum += amount;
    }

    return sum;
}

void main() {
    IO.println(applicationName);
    IO.println("Tổng chi: " + total(120_000, 80_000, 150_000));
}
~~~

Trong ví dụ này:

- **applicationName** là một field.
- **total(...)** là một method.
- **main()** là method khởi chạy chương trình.

Cả ba đều được hiểu là thành viên của cùng một lớp được khai báo ngầm. Vì vậy, **main()** có thể đọc field **applicationName** và gọi method **total(...)** như các thành viên instance thông thường.

### 3.1. Đặc điểm của lớp được khai báo ngầm

Theo Java Language Specification, lớp được khai báo ngầm trong compact source file có các đặc điểm chính:

| Đặc điểm | Ý nghĩa |
|---|---|
| Lớp cấp cao nhất **final** | Không thể được kế thừa. |
| Thuộc unnamed package | Tệp không tạo một kiểu có tên trong package do người viết khai báo. |
| Kế thừa **Object** | Không khai báo lớp cha trực tiếp khác. |
| Không triển khai interface | Không có danh sách interface được khai báo cho lớp ngầm. |
| Có constructor mặc định không tham số | Trình biên dịch cung cấp constructor này. |
| Chứa các thành viên trong tệp | Field, method và các kiểu thành viên được khai báo trực tiếp trở thành thành viên của lớp ngầm. |
| Phải có launchable **main** | Nếu không có phương thức **main** hợp lệ để khởi chạy, compact source file không hợp lệ. |

Lớp ngầm không thể được tham chiếu bằng tên trong mã nguồn. Tên lớp mà trình biên dịch dùng để tạo class file là chi tiết triển khai; không nên dựa vào tên đó để thiết kế API hoặc để lớp khác tham chiếu.

Bạn vẫn có thể dùng từ khóa **this** bên trong một instance method vì method đó thuộc về một đối tượng. Tuy nhiên, bạn không thể tự viết **new** để tạo đối tượng từ lớp ngầm, vì không có tên lớp hợp lệ để tham chiếu.

### 3.2. Các thành viên có hành vi như thành viên của lớp thông thường

Field và method trong compact source file tuân theo quy tắc thành viên lớp Java:

~~~java
private final String greeting = "Xin chào";

private String createMessage(String name) {
    return greeting + ", " + name + "!";
}

void main() {
    IO.println(createMessage("Lan"));
}
~~~

Field và method mặc định có phạm vi truy cập package và là thành viên instance nếu không có modifier **static**. Bạn vẫn có thể dùng các modifier hợp lệ như **private**, **protected**, **public**, **static** hoặc **final** tùy loại thành viên và mục đích.

Compact source file không phải nơi để khai báo constructor cho lớp ngầm. Lớp này đã có constructor mặc định không tham số do trình biên dịch cung cấp; cấu trúc của nó được thiết kế để làm điểm vào cho một chương trình độc lập.

### 3.3. Package và khả năng tái sử dụng

Lớp ngầm thuộc unnamed package và unnamed module. Điều này phù hợp với ví dụ độc lập, nhưng không phù hợp khi một kiểu cần được các package có tên tham chiếu như một API thông thường.

Vì vậy, compact source file không có khai báo **package** để đưa lớp ngầm vào một package có tên. Khi chương trình cần package, module, kiểu công khai hoặc nhiều lớp có thể tham chiếu lẫn nhau, hãy chuyển sang khai báo lớp tường minh.

## 4. Instance main methods

Trong cách khởi chạy Java truyền thống, điểm vào thường được viết như sau:

~~~java
public static void main(String[] args)
~~~

Từ Java 25, launch protocol cho phép thêm các dạng **main** hợp lệ. Một phương thức **main** có thể là instance method, có thể không nhận tham số và không bắt buộc phải khai báo **public**.

Các dạng chính được chấp nhận:

~~~java
void main() {
    IO.println("Chương trình đã bắt đầu.");
}
~~~

~~~java
void main(String[] args) {
    IO.println("Số đối số: " + args.length);
}
~~~

~~~java
static void main() {
    IO.println("Đây là static main không tham số.");
}
~~~

~~~java
public static void main(String[] args) {
    IO.println("Dạng main truyền thống vẫn hợp lệ.");
}
~~~

Một candidate **main** phải có tên **main**, kiểu trả về **void** và một trong hai dạng tham số:

- Không có tham số.
- Một tham số kiểu **String[]**; dạng varargs **String...** cũng biểu diễn cùng kiểu mảng.

Phương thức phải có thể truy cập được: **public**, **protected** hoặc package-private đều được. Phương thức **private** không phải candidate để launcher gọi.

### 4.1. Instance main hoạt động như thế nào?

Với một **static main**, launcher gọi phương thức trực tiếp trên lớp.

Với một instance **main**, launcher phải tạo một đối tượng của lớp trước, sau đó gọi phương thức trên đối tượng đó. Đối tượng được tạo bằng constructor không tham số có thể truy cập và không phải **private**.

Trong compact source file, lớp được khai báo ngầm đã có constructor mặc định không tham số, nên instance **main** có thể chạy mà người viết không cần khai báo constructor.

Instance main cũng có thể truy cập field và gọi method instance mà không cần tạo một đối tượng khác:

~~~java
private final String studentName = "Minh";

private String greeting() {
    return "Chào " + studentName;
}

void main() {
    IO.println(greeting());
}
~~~

### 4.2. Java chọn phương thức main nào?

Khi có nhiều phương thức **main**, launcher áp dụng thứ tự sau:

1. Tìm candidate **main** có một tham số **String[]** và kiểu trả về **void**.
2. Nếu không có candidate dạng trên, tìm candidate **main()** không tham số và kiểu trả về **void**.
3. Nếu không có candidate phù hợp, launcher báo lỗi và dừng.

Ở mỗi bước, phương thức được chọn có thể là **static** hoặc instance. Nếu là instance method, launcher cần tạo đối tượng bằng constructor không tham số có thể truy cập và không phải **private**.

Ví dụ, nếu một lớp có cả hai phương thức dưới đây, launcher chọn phương thức nhận **String[]**:

~~~java
void main() {
    IO.println("Không có đối số.");
}

void main(String[] args) {
    IO.println("Có " + args.length + " đối số.");
}
~~~

Sơ đồ lựa chọn:

~~~mermaid
flowchart TD
    A["Java Launcher bắt đầu"] --> B{"Có candidate main(String[]) trả về void?"}
    B -- "Có" --> C{"Phương thức static?"}
    B -- "Không" --> D{"Có candidate main() trả về void?"}
    D -- "Không" --> E["Báo lỗi khởi chạy"]
    D -- "Có" --> F{"Phương thức static?"}
    C -- "Có" --> G["Gọi trực tiếp phương thức"]
    C -- "Không" --> H["Tạo đối tượng bằng constructor 0 tham số không private"]
    F -- "Có" --> G
    F -- "Không" --> H
    H --> I["Gọi main trên đối tượng"]
~~~

Lưu ý: **String[]** được ưu tiên trước **main()** không tham số. Thứ tự này không có nghĩa là **static** luôn được ưu tiên hơn instance.

### 4.3. Constructor ảnh hưởng đến instance main

Đối với lớp tường minh, instance **main** chỉ chạy được nếu launcher có thể tạo đối tượng bằng constructor không tham số có thể truy cập.

Ví dụ sau có constructor mặc định do trình biên dịch cung cấp nên có thể khởi chạy bằng instance **main**:

~~~java
class Greeter {
    private final String name = "Lan";

    void main() {
        IO.println("Xin chào, " + name + "!");
    }
}
~~~

Nếu lớp tự khai báo constructor có tham số, trình biên dịch không còn tự cung cấp constructor mặc định. Khi đó, hãy khai báo thêm constructor không tham số phù hợp nếu muốn dùng instance **main**:

~~~java
class Greeter {
    private final String name;

    Greeter() {
        this.name = "Lan";
    }

    Greeter(String name) {
        this.name = name;
    }

    void main() {
        IO.println("Xin chào, " + name + "!");
    }
}
~~~

Constructor **private** không đáp ứng yêu cầu khởi tạo đối tượng của launch protocol. Với compact source file, bạn không tự khai báo constructor cho lớp ngầm; constructor mặc định không tham số đã được cung cấp.

## 5. Tự động import các kiểu thuộc module java.base

Compact source file tự động import theo yêu cầu tất cả kiểu lớp và interface cấp cao nhất có thể truy cập trong các package được export bởi module **java.base**. Có thể hiểu quy tắc này tương tự như việc compact source file có thêm khai báo module import cho **java.base**.

Do đó, bạn có thể dùng nhiều kiểu Java cơ bản mà không cần viết import riêng:

~~~java
void main() {
    List<String> languages = List.of("Java", "Kotlin", "Scala");

    Set<String> sortedLanguages = new TreeSet<>(languages);

    Map<Integer, String> byLength = languages.stream()
        .collect(Collectors.toMap(
            String::length,
            Function.identity()
        ));

    IO.println(sortedLanguages);
    IO.println(byLength);
}
~~~

Các kiểu như **List**, **Set**, **Map**, **TreeSet**, **Stream**, **Collectors** và **Function** thuộc những package được export bởi **java.base**, nên ví dụ trên không cần khai báo import.

Quy tắc này có phạm vi giới hạn:

- Chỉ áp dụng cho compact source file.
- Chỉ áp dụng cho các kiểu lớp và interface công khai được export bởi **java.base**.
- Không tự import mọi module của JDK.
- Không tự import các kiểu do ứng dụng hoặc thư viện bên ngoài cung cấp.
- Không tự import các static method.

Nếu cần kiểu thuộc module khác, chẳng hạn API JDBC trong **java.sql**, bạn vẫn cần khai báo import thích hợp và bảo đảm module cần thiết có mặt trong cấu hình chạy.

## 6. Console I/O với java.lang.IO

Java 25 bổ sung lớp **java.lang.IO** để đơn giản hóa thao tác nhập và xuất văn bản theo từng dòng. Lớp này tiếp tục có trong Java 27.

Các method thường dùng:

| Method | Công dụng |
|---|---|
| **IO.print(value)** | In giá trị ra đầu ra chuẩn, không tự xuống dòng. |
| **IO.println(value)** | In giá trị và kết thúc bằng ký tự xuống dòng. |
| **IO.println()** | Chỉ in ký tự xuống dòng. |
| **IO.readln()** | Đọc một dòng từ đầu vào chuẩn. |
| **IO.readln(prompt)** | In lời nhắc, sau đó đọc một dòng. |

Vì **IO** thuộc package **java.lang**, bạn có thể dùng tên lớp **IO** mà không cần import. Tuy nhiên, các method của lớp này là static method và không được tự động static import. Hãy gọi **IO.println(...)**, **IO.print(...)** hoặc **IO.readln(...)**.

### 6.1. Nhập và xuất một dòng

~~~java
void main() {
    String name = IO.readln("Tên của bạn: ");

    if (name == null) {
        IO.println("Luồng nhập đã kết thúc.");
        return;
    }

    IO.println("Xin chào, " + name + "!");
}
~~~

Ví dụ khi chạy:

~~~text
Tên của bạn: An
Xin chào, An!
~~~

**IO.readln(prompt)** in lời nhắc mà không tự xuống dòng, sau đó đọc một dòng từ đầu vào chuẩn. **IO.readln()** đọc một dòng mà không in lời nhắc.

Hai method **readln** trả về **null** nếu luồng đầu vào đã kết thúc trước khi đọc được ký tự nào. Vì vậy, chương trình có thể kiểm tra **null** trước khi xử lý chuỗi.

### 6.2. Đọc đối số dòng lệnh

Nếu chương trình cần nhận dữ liệu từ lệnh chạy, hãy dùng **main(String[] args)**:

~~~java
void main(String[] args) {
    String name = args.length > 0 ? args[0] : "bạn";
    IO.println("Xin chào, " + name + "!");
}
~~~

Chạy:

~~~bash
java Greeting.java Phuong
~~~

Kết quả:

~~~text
Xin chào, Phuong!
~~~

Các giá trị xuất hiện sau tên tệp nguồn được launcher truyền vào mảng **args**. Nếu không cần đối số dòng lệnh, có thể dùng **void main()**.

### 6.3. Lưu ý khi dùng IO.readln

**IO.readln** đọc dữ liệu từ **System.in** và có thể đệm trước một phần dữ liệu đầu vào. Sau lần gọi đầu tiên đến **IO.readln**, việc tiếp tục đọc trực tiếp từ **System.in** bằng một kỹ thuật khác có hành vi không được đặc tả.

Vì vậy, trong cùng một chương trình, hãy chọn một cách đọc đầu vào và sử dụng nhất quán. Với bài tập nhập liệu theo dòng, **IO.readln** thường đủ đơn giản. Với ứng dụng cần xử lý luồng phức tạp, hãy chọn API I/O phù hợp và kiểm soát việc đọc dữ liệu một cách rõ ràng.

## 7. Chạy compact source file trên Java 27

Để sử dụng cú pháp compact source file, hãy dùng JDK 25 trở lên. Các ví dụ trong bài hướng tới JDK 27.

Kiểm tra phiên bản công cụ:

~~~bash
java --version
javac --version
~~~

### 7.1. Chạy trực tiếp tệp nguồn

Với tệp **HelloWorld.java**:

~~~java
void main() {
    IO.println("Hello from Java 27");
}
~~~

Chạy bằng source-file mode:

~~~bash
java HelloWorld.java
~~~

Launcher biên dịch tệp nguồn và chạy chương trình trong một bước. Bạn không cần gọi **javac** trước.

### 7.2. Biên dịch rồi chạy

Bạn cũng có thể biên dịch tường minh:

~~~bash
javac HelloWorld.java
java HelloWorld
~~~

Cách này hữu ích khi muốn tách bước biên dịch và thực thi, hoặc khi cần kiểm tra lỗi biên dịch trước khi chạy.

### 7.3. Phân biệt compact source file và source-file mode

Hai khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa |
|---|---|
| Compact source file | Cách viết mã nguồn không khai báo lớp tường minh; trình biên dịch tạo một lớp được khai báo ngầm. |
| Source-file mode | Chế độ của lệnh **java** cho phép chạy trực tiếp một tệp **.java**, chẳng hạn **java HelloWorld.java**. |

Source-file mode cũng có thể chạy tệp **.java** chứa lớp được khai báo tường minh. Ngược lại, một compact source file vẫn có thể được biên dịch bằng **javac** rồi chạy bằng tên lớp do trình biên dịch tạo ra theo quy tắc của launcher.

Đừng nhầm việc chạy trực tiếp tệp **.java** với việc bỏ qua biên dịch: mã nguồn vẫn được biên dịch trước khi thực thi.

### 7.4. Không cần bật preview feature

Compact source files và instance **main** methods đã là tính năng chính thức từ Java 25. Khi dùng JDK 25 hoặc JDK 27, bạn không cần bật **--enable-preview** để dùng các ví dụ trong bài.

Các tên gọi và hành vi xuất hiện trong những bản preview trước Java 25 có thể khác bản chính thức. Đặc biệt, trong cú pháp hiện hành, hãy gọi **IO.println(...)** thay vì viết trần **println(...)**. Lớp **IO** hiện thuộc **java.lang**, và các static method của nó không được tự động import.

## 8. Instance main trong lớp tường minh

Instance **main** không chỉ dành cho compact source file. Bạn cũng có thể khai báo nó trong một lớp Java thông thường:

~~~java
class Welcome {
    private final String message = "Chào mừng đến với Java 27";

    void main() {
        IO.println(message);
    }
}
~~~

Lưu đoạn mã vào **Welcome.java** và chạy:

~~~bash
java Welcome.java
~~~

Trong ví dụ này:

- **Welcome** là lớp được khai báo tường minh.
- **message** là field instance.
- **main()** là instance method, không có **static**.
- Launcher tạo đối tượng **Welcome** bằng constructor không tham số mặc định, sau đó gọi **main()** trên đối tượng đó.

Instance main hữu ích khi điểm khởi chạy cần làm việc với trạng thái instance đã được khởi tạo. Tuy vậy, hãy cân nhắc yêu cầu tương thích của framework, công cụ đóng gói và môi trường triển khai trước khi dùng nó làm entry point của ứng dụng lớn.

## 9. Khi nào nên dùng compact source file?

| Tình huống | Cách phù hợp |
|---|---|
| Bài tập đầu tiên về biến, điều kiện, vòng lặp và method | Compact source file giúp tập trung vào logic đang học. |
| Ví dụ ngắn trong tài liệu hoặc buổi trình diễn | Có thể bỏ phần khai báo lớp chưa cần thiết. |
| Thử nghiệm một ý tưởng bằng một tệp | Có thể chạy trực tiếp bằng **java File.java**. |
| Chương trình cần nhiều lớp có tên và được tham chiếu qua lại | Dùng lớp tường minh và package có tên. |
| Thư viện cung cấp API cho module hoặc ứng dụng khác | Dùng kiểu có tên, package và module rõ ràng. |
| Ứng dụng dựa vào framework hoặc công cụ yêu cầu entry point theo quy ước riêng | Kiểm tra khả năng hỗ trợ của framework; thường nên dùng entry point tường minh theo yêu cầu của công cụ. |

Compact source file vẫn có các giới hạn cấu trúc: lớp ngầm thuộc unnamed package, không thể được tham chiếu bằng tên từ mã nguồn và không đại diện cho một API công khai có thể tái sử dụng. Công cụ **javadoc** cũng không thể tạo tài liệu API cho chính lớp được khai báo ngầm như đối với một lớp có tên thông thường.

Một chương trình bắt đầu bằng compact source file vẫn có thể phát triển thành chương trình có cấu trúc. Khi cần lớp có tên, hãy chuyển các field và method vào phần thân của một lớp tường minh, đồng thời đặt các import ở đầu tệp:

~~~java
import java.util.List;

public class GreetingApp {
    private final String greeting = "Xin chào";
    private final List<String> supportedLanguages = List.of("Java", "Kotlin");

    public static void main(String[] args) {
        GreetingApp app = new GreetingApp();
        app.run(args);
    }

    private void run(String[] args) {
        String name = args.length > 0 ? args[0] : "bạn";
        System.out.println(greeting + ", " + name + "!");
        System.out.println("Ngôn ngữ hỗ trợ: " + supportedLanguages);
    }
}
~~~

Đây là cấu trúc phù hợp hơn khi chương trình cần một kiểu có tên, được tạo đối tượng từ nơi khác hoặc được tích hợp vào một ứng dụng nhiều thành phần. Dạng **public static void main(String[] args)** vẫn hoàn toàn hợp lệ và là lựa chọn quen thuộc cho nhiều ứng dụng.

## 10. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Cách xử lý |
|---|---|
| Nghĩ rằng mọi chương trình Java bắt buộc phải có **public static void main(String[] args)** | Dạng truyền thống vẫn hợp lệ; Java 25+ còn chấp nhận các candidate **main** khác theo launch protocol. |
| Khai báo **private void main()** rồi mong launcher gọi được | Dùng **public**, **protected** hoặc package-private. |
| Khai báo **int main()** hoặc **String main()** | Candidate **main** phải trả về **void**. |
| Dùng instance **main** trong lớp có constructor chỉ nhận tham số | Bổ sung constructor không tham số có thể truy cập, hoặc dùng static main. |
| Khai báo constructor **private** cho lớp có instance main | Launcher không thể tạo đối tượng bằng constructor đó; cần constructor không tham số không private. |
| Viết **println("Hello")** trong compact source file | Dùng **IO.println("Hello")**, hoặc khai báo static import rõ ràng. |
| Nghĩ rằng compact source file tự import mọi thư viện trong JDK | Chỉ các kiểu công khai được export bởi **java.base** được tự động import. |
| Nghĩ rằng instance main chỉ hoạt động khi không có khai báo lớp | Instance main cũng hoạt động trong lớp tường minh. |
| Cố tham chiếu lớp ngầm bằng tên tệp hoặc thêm nó vào package có tên | Lớp ngầm thuộc unnamed package và không thể được tham chiếu bằng tên trong mã nguồn. |
| Dùng **--enable-preview** theo hướng dẫn cũ | Với JDK 25 trở lên, JEP 512 đã là tính năng chính thức, không cần bật preview. |

## 11. Ghi nhớ

- **Compact source file** cho phép khai báo field và method trực tiếp mà không cần viết lớp tường minh.
- Trình biên dịch tạo một lớp cấp cao nhất được khai báo ngầm; lớp này **final**, thuộc unnamed package và có constructor mặc định không tham số.
- **Instance main** là phương thức khởi chạy không cần **static**; nó có thể không nhận tham số và không bắt buộc **public**.
- Candidate **main** phải trả về **void**, có quyền truy cập **public**, **protected** hoặc package-private, và nhận **String[]** hoặc không nhận tham số.
- Launcher ưu tiên **main(String[])** trước **main()**. Với instance main, launcher cần tạo được đối tượng bằng constructor không tham số không private.
- Compact source file tự động import các kiểu công khai được export bởi **java.base**; static method không được tự động import.
- Dùng **IO.print**, **IO.println** và **IO.readln** cho thao tác console theo dòng đơn giản.
- JEP 512 là tính năng chính thức từ Java 25 và được hỗ trợ trong Java 27; không cần preview flag.
- Khi cần package, API tái sử dụng hoặc cấu trúc ứng dụng nhiều thành phần, hãy dùng lớp tường minh.

## Tài liệu tham khảo

- [Oracle Java SE 27 — Compact Source Files and Instance main Methods](https://docs.oracle.com/en/java/javase/27/language/compact-source-files-instance-main-methods.html)
- [Oracle Java SE 27 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html)
- [Oracle Java SE 27 — Java Language Changes Summary](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html)
- [Oracle Java SE 27 API — java.lang.IO](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/IO.html)
- [OpenJDK JEP 512 — Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512)
