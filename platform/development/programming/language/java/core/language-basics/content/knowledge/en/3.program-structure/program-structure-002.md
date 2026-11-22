# Vai trò của `public static void main(String[] args)` trong Java

Khi chạy một ứng dụng Java đơn giản từ terminal, JVM cần biết **chương trình bắt đầu thực thi từ đâu**. Với cách khởi chạy một lớp thông thường trên **JDK 17**, Java launcher tìm một phương thức có chữ ký phù hợp, điển hình là:

~~~java
public static void main(String[] args)
~~~

Phương thức `main` là **điểm vào (entry point)** của chương trình. Những câu lệnh trong phần thân `main` được gọi khi người dùng chạy lớp đó bằng lệnh `java`. Nó không phải toàn bộ ứng dụng: từ `main`, bạn có thể gọi những phương thức và lớp khác để thực hiện công việc.

Bài này tập trung vào chữ ký trên, cách chạy lớp chứa `main`, vai trò của đối số `args` và những lỗi người mới thường gặp. Các ví dụ dùng **JDK 17 trở lên** và cú pháp `main` truyền thống tương thích Java 17.

## 1. Đọc từng phần của chữ ký `main`

| Thành phần | Ý nghĩa | Tại sao cần trong cách chạy lớp trên Java 17? |
| --- | --- | --- |
| `public` | Phương thức có khả năng truy cập công khai | Java launcher cần có thể gọi điểm vào |
| `static` | Phương thức thuộc lớp, không cần tạo đối tượng để gọi | Launcher có thể gọi `main` mà không phải `new` lớp chứa nó |
| `void` | Phương thức không trả về một giá trị Java | Chữ ký entry point truyền thống yêu cầu trả về `void` |
| `main` | Tên phương thức điểm vào | Launcher tìm phương thức có tên này |
| `String[]` | Kiểu **mảng các chuỗi** | Chứa đối số người dùng truyền khi chạy chương trình |
| `args` | Tên tham số của mảng `String[]` | Tên có thể đổi; `args` chỉ là quy ước dễ hiểu |

Từ khóa `public`, `static` và `void` không phải ba từ viết cho đẹp: bỏ hoặc thay sai có thể khiến phương thức **không còn đáp ứng yêu cầu điểm vào**, dù lớp vẫn biên dịch.

Ví dụ, một phương thức thông thường cũng có thể có tên `main` nhưng không nhất thiết được Java launcher dùng làm điểm vào:

~~~java
static void main(int number) {
    System.out.println(number);
}
~~~

Đó là một phương thức có tham số `int`, **không** phải chữ ký `main(String[] args)` mà ví dụ chạy lớp dưới đây yêu cầu.

### Vì sao `main` có `static`?

Một phương thức `static` có thể được gọi theo tên lớp mà không cần tạo instance. Khi khởi động `GreetingMain`, launcher không cần biết cách tạo `new GreetingMain()`; nó dùng phương thức `main` phù hợp để bắt đầu luồng thực thi.

Từ khóa `static` ở đây **không có nghĩa** toàn bộ dữ liệu của ứng dụng phải là biến `static`. Bạn vẫn có thể tạo đối tượng, gọi phương thức instance và tổ chức chương trình thành nhiều lớp từ `main`.

## 2. Một chương trình Java 17+ hoàn chỉnh

Tạo tệp **`GreetingMain.java`** với nội dung sau:

~~~java
public class GreetingMain {
    public static void main(String[] args) {
        if (args.length != 2) {
            System.out.println(
                    "Cach dung: java GreetingMain <ten> <soLan>");
            return;
        }

        String name = args[0];
        if (name.isBlank()) {
            System.out.println("Loi: ten khong duoc trong");
            return;
        }

        final int times;
        try {
            times = Integer.parseInt(args[1]);
        } catch (NumberFormatException ex) {
            System.out.println("Loi: soLan phai la so nguyen");
            return;
        }

        if (times < 1 || times > 5) {
            System.out.println("Loi: soLan phai tu 1 den 5");
            return;
        }

        for (int i = 1; i <= times; i++) {
            System.out.println(
                    "Lan " + i + ": Xin chao, " + name + "!");
        }
    }
}
~~~

Ví dụ này cố ý chỉ có **một lớp công khai** chứa một điểm vào.

- `public class GreetingMain`: tên lớp phải khớp với tên tệp `GreetingMain.java`.
- `main`: nhận hai đối số, kiểm tra dữ liệu và quyết định cần làm gì.
- `args.length`: số **chuỗi đối số**, không bao gồm từ `java` hay tên lớp.
- `args[0]`: tên người được chào; `args[1]`: văn bản cần chuyển thành số lần lặp.
- `Integer.parseInt(args[1])`: chuyển chuỗi số nguyên; dữ liệu như `abc` hoặc số vượt miền `int` gây `NumberFormatException`.
- `return;`: kết thúc lời gọi `main` hiện tại, không trả về giá trị vì `main` có kiểu `void`.
- Vòng `for` thực hiện in đúng số lần, sau khi dữ liệu được xác nhận trong khoảng 1–5.

Chữ ký phương thức **đúng** chưa đủ để chương trình đúng nghiệp vụ. Việc kiểm tra số đối số, tên trống và số lần hợp lệ là trách nhiệm của mã trong `main`.

## 3. Biên dịch và chạy bằng terminal

Mở PowerShell trên Windows hoặc Bash trên Linux, đi tới thư mục có `GreetingMain.java`.

### Kiểm tra công cụ

~~~bash
java -version
javac -version
~~~

Dùng JDK 17 trở lên có `java` và `javac`. Tạo thư mục riêng cho bytecode:

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
~~~

**Linux/Bash:**

~~~bash
mkdir -p out
~~~

Sau đó, trên **cả hai hệ điều hành**:

~~~bash
javac -encoding UTF-8 -d out GreetingMain.java
java -cp out GreetingMain Mai 3
~~~

**Kết quả:**

~~~text
Lan 1: Xin chao, Mai!
Lan 2: Xin chao, Mai!
Lan 3: Xin chao, Mai!
~~~

`javac` tạo `out/GreetingMain.class` khi mã hợp lệ; `-d out` yêu cầu output vào thư mục đó. Lệnh `java -cp out GreetingMain Mai 3` dùng Java launcher để tìm lớp `GreetingMain` trong classpath `out` rồi gọi phương thức `main` tương ứng.

Với lệnh trên, launcher truyền vào `main`:

~~~text
args.length == 2
args[0] == "Mai"
args[1] == "3"
~~~

Điều đó có nghĩa **`args[1]` vẫn là `String`** `"3"`, dù khi gõ lệnh trông giống một con số. Chỉ khi gọi `Integer.parseInt`, chương trình mới thu được giá trị `int` là 3.

### Tên chứa dấu cách vẫn là một đối số

~~~bash
java -cp out GreetingMain "Lan Anh" 2
~~~

~~~text
Lan 1: Xin chao, Lan Anh!
Lan 2: Xin chao, Lan Anh!
~~~

PowerShell và Bash đều hiểu dấu nháy kép ở đây để giữ `Lan Anh` thành **một đối số**. Nếu bỏ dấu nháy, shell thường tách thành hai đối số `Lan` và `Anh`, làm `args.length` thay đổi.

## 4. Dòng thực thi đi qua `main` như thế nào?

~~~mermaid
flowchart TD
    A["java -cp out GreetingMain Mai 3"] --> B["Java launcher tìm GreetingMain"]
    B --> C["Tìm main(String[] args) phù hợp"]
    C --> D["Gọi main với 2 chuỗi đối số"]
    D --> E{"Dữ liệu hợp lệ?"}
    E -->|Không| F["In lỗi hoặc hướng dẫn, return"]
    E -->|Có| G["Chạy vòng for, in lời chào"]
    G --> H["Kết thúc lời gọi main"]
~~~

Một ứng dụng lớn hơn vẫn dùng `main` làm nơi **khởi động và kết nối các thành phần**; không nên dồn mọi phép tính và mọi thao tác I/O vào một phương thức rất dài chỉ vì `main` là điểm vào.

`main` thường được gọi lúc bắt đầu luồng chính trong ví dụ chạy lớp, nhưng **không nhất thiết là phương thức duy nhất được thực thi**. Nó có thể gọi các phương thức khác. Nếu chương trình tạo thêm luồng còn hoạt động, việc `main` trả về **không tự bảo đảm JVM dừng ngay lập tức**.

## 5. `args` là gì và không phải là gì?

### `args` chỉ là tên biến tham số

Hai chữ ký sau cùng mô tả tham số `String[]`:

~~~java
public static void main(String[] args)
~~~

~~~java
public static void main(String[] arguments)
~~~

Tên `args` được sử dụng rộng rãi, nhưng **không phải từ khóa**. Nếu đổi tên thành `arguments`, bạn phải đổi các chỗ sử dụng bên trong phương thức.

Java còn chấp nhận cú pháp tham số biến độ dài (*varargs*) cho kiểu chuỗi:

~~~java
public static void main(String... args)
~~~

Ở bên trong, `args` vẫn sử dụng được như một mảng `String[]`. Với người mới học, cách viết `String[] args` thường rõ ràng hơn.

### Giá trị ban đầu của `args`

Khi khởi chạy bình thường qua Java launcher, chương trình nhận mảng chứa những đối số sau tên lớp. Không cung cấp đối số nghĩa là mảng có **độ dài 0**:

~~~bash
java -cp out GreetingMain
~~~

Kết quả từ chương trình ví dụ:

~~~text
Cach dung: java GreetingMain <ten> <soLan>
~~~

**Không đọc `args[0]` trước khi kiểm tra `args.length`.** Nếu mảng không có phần tử, truy cập chỉ số 0 sẽ gây `ArrayIndexOutOfBoundsException` khi chạy.

Một phương thức Java có thể được gọi thủ công trong mã khác bằng `GreetingMain.main(null)`, nhưng đó là lời gọi khác với việc khởi động thông thường. Vì vậy, không nên suy luận rằng mọi lời gọi trực tiếp tới `main` đều tự có mảng hợp lệ.

## 6. Phân biệt lỗi chữ ký điểm vào với lỗi dữ liệu trong `main`

| Vấn đề | Biên dịch `javac`? | Khi chạy `java`? |
| --- | --- | --- |
| `public static void main(String[] args)` | Hợp lệ | Launcher dùng làm điểm vào |
| Chỉ có `public void main(String[] args)` | Lớp vẫn có thể biên dịch | Trên Java 17, không phải entry point phù hợp vì thiếu `static` |
| Chỉ có `private static void main(String[] args)` | Lớp vẫn có thể biên dịch | Trên Java 17, không phải entry point phù hợp vì không `public` |
| Chỉ có `public static int main(String[] args)` | Có thể biên dịch như method thường | Không đúng kiểu trả về `void` của entry point Java 17 |
| Chỉ có `public static void main(int[] args)` | Có thể biên dịch như method thường | Không khớp tham số mảng `String` |
| `args[0]` khi không có đối số | Vẫn có thể biên dịch | Có thể ném `ArrayIndexOutOfBoundsException` |
| `Integer.parseInt("abc")` | Hợp lệ về kiểu | Ném `NumberFormatException` lúc chạy |

**Quan trọng:** `javac` không yêu cầu **mọi lớp** đều phải có `main`. Một lớp thư viện hoặc lớp dữ liệu có thể biên dịch bình thường mà không thể chạy trực tiếp bằng `java TenLop` theo cách thông thường.

Thông báo từ Java launcher có thể khác giữa các bản JDK, nhưng nguyên tắc là: **biên dịch hợp lệ** và **có điểm vào hợp lệ để chạy lớp** là hai kiểm tra khác nhau.

Một chữ ký hợp lệ chỉ định **cách bắt đầu**, không kiểm tra số lượng hay kiểu số học của đối số: các chuỗi đầu vào vẫn cần được phân tích trong ứng dụng.

## 7. Những ca cần thử với chương trình mẫu

| Lệnh sau khi biên dịch | Kết quả cần kiểm chứng |
| --- | --- |
| `java -cp out GreetingMain Mai 1` | In một lời chào |
| `java -cp out GreetingMain Mai 5` | In năm lời chào |
| `java -cp out GreetingMain Mai 0` | `Loi: soLan phai tu 1 den 5` |
| `java -cp out GreetingMain Mai 6` | `Loi: soLan phai tu 1 den 5` |
| `java -cp out GreetingMain Mai abc` | `Loi: soLan phai la so nguyen` |
| `java -cp out GreetingMain Mai 2147483648` | `Loi: soLan phai la so nguyen` vì ngoài miền `int` |
| `java -cp out GreetingMain Mai` | In hướng dẫn vì thiếu đối số |
| `java -cp out GreetingMain "Lan Anh" 2` | Hai lời chào với đúng tên có dấu cách |
| `java -cp out GreetingMain "" 2` | `Loi: ten khong duoc trong` |

Một tình huống khác: nếu truyền `" 2 "` làm chuỗi số lần, `Integer.parseInt` không mặc nhiên loại bỏ khoảng trắng. Khi muốn chấp nhận khoảng trắng, ứng dụng phải có quy tắc xử lý như `trim()` rõ ràng. Đừng sửa mã chỉ để thông qua một ca kiểm thử mà chưa quyết định hành vi đầu vào được mong đợi.

### Tại sao `return;` không giống `System.exit(...)`?

Trong mã ví dụ, `return;` chỉ **kết thúc phương thức `main`**. Với chương trình đơn luồng đơn giản, không còn tác vụ khác nên chương trình thường kết thúc ngay sau đó.

Ngược lại, `System.exit(2)` yêu cầu JVM kết thúc tiến trình với mã trạng thái 2; điều này thường hữu ích cho công cụ CLI hoặc hệ thống tự động hóa khi cần phân biệt thành công và lỗi. Nó có tác động lên **toàn tiến trình**, nên không cần dùng khi bài học chỉ đang trình bày vai trò cơ bản của `main`.

Vì ví dụ hiện tại in lỗi rồi `return;`, nó **không tự đặt mã thoát khác 0**. Đừng giả định cứ in chữ `Loi` thì shell sẽ thấy tiến trình thất bại.

## 8. Bài tập tự luyện

**Bài 1 — Giải thích chữ ký.** Không nhìn bảng, hãy nói một câu cho mỗi thành phần `public`, `static`, `void`, `main`, `String[]` và `args`.

**Bài 2 — Dự đoán kết quả.** Chạy `java -cp out GreetingMain "Minh Chau" 2`. Có bao nhiêu phần tử trong `args`? Hai phần tử chứa gì và có bao nhiêu dòng được in?

*Đáp án:* Hai phần tử, `"Minh Chau"` và `"2"`; hai lời chào.

**Bài 3 — Tìm lỗi điểm vào.** Hãy thử đổi `public static void main(String[] args)` thành `public void main(String[] args)`. Tại sao `javac` có thể không báo lỗi nhưng `java -cp out GreetingMain Mai 2` không chạy theo ý định trên Java 17?

*Đáp án:* Bạn tạo một phương thức instance, không còn phương thức `main` `public static` đúng chữ ký mà launcher Java 17 tìm.

**Bài 4 — Xử lý input.** Sửa mã để chấp nhận số lần từ 1 đến 10, rồi chạy ca đúng ngưỡng 10 và ca sai 11. Xác nhận chỉ thay đổi quy tắc kiểm tra số lần, không làm thay đổi ý nghĩa `main`.

**Bài 5 — Tách công việc khỏi `main`.** Thêm phương thức sau **bên trong lớp `GreetingMain`**:

~~~java
static void greet(String name, int sequence) {
    System.out.println(
            "Lan " + sequence + ": Xin chao, " + name + "!");
}
~~~

Sau đó thay câu `println` trong vòng `for` bằng `greet(name, i);`. Kết quả có thay đổi không? Giải thích vì sao đây là một bước tổ chức mã tốt dù `main` vẫn là điểm vào.

## Checklist ghi nhớ

- [ ] Biết rằng `main` là điểm vào khi Java launcher chạy lớp theo cách truyền thống trên JDK 17.
- [ ] Giải thích được `public`, `static`, `void`, `main`, `String[]`, `args`.
- [ ] Tạo đúng tệp chứa `public class` và biên dịch bằng `javac`.
- [ ] Chạy được `java -cp out GreetingMain Mai 3` và dự đoán được kết quả.
- [ ] Biết đối số CLI ban đầu đều là `String` và tên lớp không nằm trong `args[]`.
- [ ] Kiểm tra `args.length` trước khi truy cập phần tử.
- [ ] Phân biệt lỗi không tìm thấy entry point với lỗi dữ liệu trong phương thức `main`.
- [ ] Hiểu rằng kết thúc `main` không phải lúc nào cũng buộc mọi luồng/JVM dừng tức thì.

**Tóm lại:** `public static void main(String[] args)` là lời khai báo điểm bắt đầu quen thuộc của ứng dụng Java 17. Java launcher sử dụng chữ ký này để gọi mã của bạn; còn chương trình dùng `args` để nhận chuỗi đầu vào. Hiểu ranh giới ấy giúp bạn tạo chương trình chạy được, phân tích lỗi đúng chỗ và tổ chức logic ngoài `main` khi ứng dụng lớn dần.
