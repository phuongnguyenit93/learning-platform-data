# Phân biệt tùy chọn launcher với tham số ứng dụng khi chạy chương trình Java từ tệp nguồn

## 1. Hai nhóm đối số trong cùng một lệnh `java`

Từ **Java 11**, Java launcher hỗ trợ chạy trực tiếp tệp mã nguồn có phần mở rộng `.java`, ví dụ `java LauncherArgsDemo.java`. Cơ chế này tiếp tục được hỗ trợ trên các JDK hiện đại. Khi chạy theo cách đó, một dòng lệnh có dạng:

```text
java [tùy chọn của launcher/JVM] LauncherArgsDemo.java [tham số ứng dụng...]
```

Trong ví dụ trên, **`LauncherArgsDemo.java` là ranh giới** giữa hai phần:

- **Trước tên tệp nguồn**: `java` xử lý các tùy chọn của launcher/JVM như `-Dkey=value` (system property), `-Xmx256m` (giới hạn heap), `--class-path` hoặc `-cp` (classpath), `--module-path` (module path), `--source` (phiên bản nguồn dùng cho chế độ chạy mã nguồn). Một số tùy chọn có đối số đi kèm, chẳng hạn `--source 17`.
- **Sau tên tệp nguồn**: các đối số của chương trình được truyền vào `String[] args` của phương thức `main`. Chuỗi có hình thức giống tùy chọn JVM, ví dụ `-Dkey=value` hoặc `-Xmx256m`, cũng chỉ là **chuỗi đối số ứng dụng** nếu đứng sau `.java`.

Phân biệt này quyết định **ai tiêu thụ đối số**: Java launcher/JVM hay mã của ứng dụng. `--port`, `--input`, `--verbose` là các ví dụ về cờ do *ứng dụng tự quy ước*; Java không tự hiểu chúng và cũng không tự chuyển chúng thành cấu hình.

## 2. Ví dụ Java 11+ chạy được

Tạo tệp **`LauncherArgsDemo.java`** với nội dung sau:

```java
public class LauncherArgsDemo {
    public static void main(String[] args) {
        System.out.println("env=" + System.getProperty("demo.env", "unset"));
        System.out.println("count=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "]=" + args[i]);
        }
    }
}
```

Chương trình đọc một **system property** bằng `System.getProperty` và lần lượt in các **tham số ứng dụng** từ `args`. Đây là hai nguồn dữ liệu khác nhau. Dùng JDK **11 trở lên**, mở terminal tại thư mục chứa tệp và thực hiện các lệnh sau. Không cần chạy `javac` trước vì Java launcher có thể biên dịch và chạy tệp nguồn trực tiếp.

### Trường hợp A — `-D` đứng trước tệp nguồn

```bash
java -Ddemo.env=dev LauncherArgsDemo.java --port 8080
```

Kết quả chính xác:

```text
env=dev
count=2
args[0]=--port
args[1]=8080
```

Giải thích: launcher xử lý `-Ddemo.env=dev` nên `System.getProperty("demo.env")` trả về `dev`. Hai đối số `--port` và `8080` đứng sau tên tệp nên được chuyển đến `main(String[] args)`. Chương trình **chưa** xử lý giá trị cổng; nó mới in hai chuỗi.

### Trường hợp B — cùng chuỗi `-D` nhưng đặt sau tệp nguồn

```bash
java LauncherArgsDemo.java -Ddemo.env=dev --port 8080
```

Kết quả chính xác (khi chưa đặt `demo.env` bằng cách khác):

```text
env=unset
count=3
args[0]=-Ddemo.env=dev
args[1]=--port
args[2]=8080
```

Lúc này `-Ddemo.env=dev` **không cấu hình system property** vì đã nằm trong phần tham số ứng dụng. Java không tự phân tích chuỗi này như tùy chọn JVM sau khi đã chọn tệp nguồn để chạy. Đây là nguyên nhân thường gặp khi một ứng dụng đọc `System.getProperty(...)` mà không thấy giá trị mong đợi.

### Trường hợp C — tham số trông giống tùy chọn launcher

```bash
java -Ddemo.env=prod LauncherArgsDemo.java -Xmx512m "--profile name"
```

Kết quả chính xác:

```text
env=prod
count=2
args[0]=-Xmx512m
args[1]=--profile name
```

`-Xmx512m` đứng **sau** tệp nguồn nên không đặt giới hạn heap thành 512 MB. Nó chỉ là `args[0]`. Dấu ngoặc kép giữ chuỗi có khoảng trắng `--profile name` thành một đối số khi shell xử lý dòng lệnh; dấu ngoặc kép không nằm trong giá trị `args[1]`.

## 3. Bảng nhận diện nhanh

| Lệnh | Phần Java launcher/JVM xử lý | Phần chương trình nhận |
| --- | --- | --- |
| `java -Ddemo.env=dev LauncherArgsDemo.java hello` | `-Ddemo.env=dev` | `args[0] = "hello"` |
| `java LauncherArgsDemo.java -Ddemo.env=dev` | Không có `-D` trước tệp | `args[0] = "-Ddemo.env=dev"` |
| `java -Xmx256m LauncherArgsDemo.java -Xmx1g` | `-Xmx256m` | `args[0] = "-Xmx1g"` |
| `java --source 17 LauncherArgsDemo.java --source 11` | `--source 17` | `args[0] = "--source"`, `args[1] = "11"` |
| `java LauncherArgsDemo.java --help` | Chạy tệp nguồn | `args[0] = "--help"` |
| `java --help` | In trợ giúp của Java launcher | Không chạy ứng dụng |

Dòng dùng `--source 17` yêu cầu JDK hỗ trợ mức nguồn 17 (ví dụ JDK 17 trở lên ở những phiên bản vẫn hỗ trợ mức này). Đây là tùy chọn xác định mức ngôn ngữ/API của mã nguồn được biên dịch, **không** có nghĩa thay đổi JDK đang chạy thành JDK 17. Với chương trình ví dụ, có thể bỏ hẳn `--source` và chỉ chạy `java LauncherArgsDemo.java`.

## 4. Tùy chọn có giá trị đi kèm phải đặt đúng phía

Một số tùy chọn của launcher có giá trị nằm ở token tiếp theo:

```text
java --class-path "libs/*" LauncherArgsDemo.java input.txt
     └──── launcher ─────┘ └─ tệp nguồn ─┘ └─ args[0] ─┘
```

Ở đây, `--class-path` và `"libs/*"` thuộc cấu hình lớp/thư viện cho Java launcher, còn `input.txt` là tham số ứng dụng. Thư mục `libs` chỉ là ví dụ cho trường hợp chương trình thật có thư viện ngoài; **chương trình mẫu ở trên không cần classpath tùy chỉnh**.

Nếu chuyển `--class-path` ra sau `.java`, ví dụ:

```bash
java LauncherArgsDemo.java --class-path libs
```

thì ứng dụng chỉ nhận `args[0] = "--class-path"` và `args[1] = "libs"`. Classpath của launcher không được thay đổi bởi hai chuỗi này.

Tương tự, `--source 17` phải nằm trước tên tệp nguồn nếu muốn áp dụng khi launcher biên dịch nguồn. Các lựa chọn cấu hình runtime như `-D` hoặc `-Xmx` cũng phải nằm trước tên tệp. Nếu một tùy chọn đứng trước tệp nhưng cần giá trị, giá trị đó **vẫn thuộc về tùy chọn**, không phải tên tệp hay tham số của `main`.

## 5. `--help` và các cờ ứng dụng dễ gây nhầm lẫn

Hai lệnh dưới đây có mục đích khác nhau:

```bash
java --help
java LauncherArgsDemo.java --help
```

Lệnh đầu yêu cầu Java launcher hiển thị hướng dẫn về lệnh `java`. Lệnh thứ hai **chạy ứng dụng**, và với chương trình mẫu, `args` chứa duy nhất chuỗi `"--help"`:

```text
env=unset
count=1
args[0]=--help
```

Java launcher không tự tạo trang trợ giúp cho ứng dụng. Nếu muốn `--help`, `--port 8080` hay `--verbose` có ý nghĩa nghiệp vụ, **mã ứng dụng hoặc thư viện phân tích tham số của nó** phải chủ động đọc `args` và triển khai ý nghĩa tương ứng.

Với chương trình đơn giản, có thể tự nhận diện một cờ:

```java
for (String arg : args) {
    if ("--verbose".equals(arg)) {
        System.out.println("Verbose mode requested");
    }
}
```

Đây là một đoạn mã minh họa **bên trong `main`**, không phải một chương trình Java độc lập mới. Nó cho thấy việc diễn giải cờ do ứng dụng quyết định, thay vì do JVM thực hiện.

## 6. Cơ chế và cách kiểm tra khi kết quả khác mong đợi

Quá trình xử lý dòng lệnh có thể hiểu theo thứ tự:

1. **Shell** xử lý cú pháp dòng lệnh trước: khoảng trắng, dấu ngoặc kép, mở rộng biến và các quy tắc riêng của shell. Vì vậy `"hello world"` thường được truyền dưới dạng một đối số.
2. **Java launcher** nhận các token kết quả, phân tích tùy chọn của mình cho đến phần chỉ định chương trình cần chạy: tệp `.java` trong chế độ source-file.
3. **Launcher/JVM** chuẩn bị môi trường thực thi, biên dịch nguồn nếu cần và gọi điểm vào của chương trình.
4. **Ứng dụng** nhận các đối số sau tệp nguồn trong `main(String[] args)`, rồi tự quyết định cách dùng chúng.

Lưu ý chính xác: một số cơ chế như **`@argument-file`** có thể được launcher mở rộng theo quy tắc riêng, nên “các đối số sau tên tệp được truyền vào `args`” nên hiểu trên danh sách đối số đã qua xử lý dòng lệnh; không suy luận rằng mọi ký tự người dùng gõ sẽ được giữ nguyên tuyệt đối.

Khi gỡ lỗi, hãy thực hiện theo trình tự:

1. Xác định chính xác tên tệp `.java` đóng vai trò ranh giới giữa hai phần của lệnh.
2. Kiểm tra `-D`, `-Xmx`, `--source`, `-cp` và các tùy chọn Java khác có nằm **trước** ranh giới đó không.
3. In `System.getProperty("key")` hoặc kiểm tra cấu hình runtime bằng công cụ thích hợp khi cần xác nhận tùy chọn JVM.
4. In `args.length` và từng `args[i]` để kiểm tra chương trình thực sự nhận những chuỗi nào.
5. Nếu có tham số ứng dụng nhiều từ, dùng cú pháp trích dẫn phù hợp với shell đang chạy.

## 7. Những hiểu lầm cần tránh

- **“`-D` đặt ở đâu cũng được.”** Sai. Sau tên tệp nguồn, `-D...` trở thành tham số của `main`.
- **“`--port 8080` sẽ tự đổi cổng của JVM.”** Sai. Đây là hai chuỗi mà ứng dụng phải tự xử lý. Ý nghĩa của chúng tùy chương trình.
- **“`-Xmx512m` sau `.java` giới hạn heap.”** Sai. Muốn điều chỉnh heap, đặt tùy chọn đó trước tệp nguồn.
- **“Chạy trực tiếp `.java` nghĩa là Java không biên dịch.”** Sai. Launcher biên dịch mã nguồn để chạy; cơ chế này không yêu cầu bước `javac` thủ công và thường không tạo `.class` trong thư mục nguồn cho ví dụ đơn giản.
- **“Source-file mode vĩnh viễn chỉ đọc đúng một tệp nguồn.”** Không chính xác với các JDK hiện đại có hỗ trợ giải quyết thêm nguồn phụ thuộc. Bài này dùng **một tệp** để minh họa cú pháp và ranh giới đối số; nguyên tắc phân biệt launcher và `args` vẫn giữ nguyên.
- **“`--source` luôn chấp nhận mọi số phiên bản Java.”** Sai. Mức nguồn được hỗ trợ phụ thuộc JDK đang chạy; nên tra `java --help` hoặc tài liệu phù hợp nếu cần chỉ định phiên bản.

**Ghi nhớ:** Trong lệnh `java [options] File.java [args...]`, vị trí của **`File.java`** quyết định ranh giới. Tùy chọn launcher/JVM phải đứng trước tệp; tham số ứng dụng đứng sau tệp và được chương trình đọc qua `main(String[] args)`. Quy tắc này vẫn hữu ích khi chạy mã nguồn trực tiếp bằng các JDK hiện đại.
