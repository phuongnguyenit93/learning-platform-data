# Phân biệt tham số JVM với đối số chương trình trong Java

Khi chạy Java bằng terminal, bạn có thể thấy một lệnh như sau:

~~~bash
java -Xmx128m -Dstudy.mode=lab -cp out ArgsBoundaryDemo 45 "Java core" --check
~~~

Ở đây, `-Xmx128m` và `-Dstudy.mode=lab` là các tùy chọn cấu hình môi trường chạy Java. `-cp out` cho **Java launcher** biết nơi tìm lớp. Trong khi đó, `45`, `Java core` và `--check` là **đối số của chương trình**; chúng được truyền đến `main(String[] args)`.

Bài học này giúp bạn nhận ra **ranh giới giữa phần cấu hình chạy Java và dữ liệu do ứng dụng nhận**. Ví dụ sử dụng **JDK 17 trở lên**, chỉ cần terminal Windows PowerShell hoặc Linux và một tệp nguồn Java.

## 1. Nhìn cấu trúc lệnh từ trái sang phải

Ở dạng chạy một lớp đã biên dịch, lệnh thường có cấu trúc:

~~~text
java [tùy chọn cho launcher/JVM] TênLớp [đối số chương trình]
        ^                           ^         ^
        cấu hình                điểm bắt đầu  args[]
~~~

Trong ví dụ:

~~~text
java -Xmx128m -Dstudy.mode=lab -cp out ArgsBoundaryDemo 45 "Java core" --check
     └──────── tùy chọn ────────┘    └lớp───┘ └──── args[] ────────┘
~~~

Một số tài liệu gọi chung các phần trước tên lớp là **“JVM arguments”**. Cách gọi này tiện trong hội thoại, nhưng nên phân biệt chính xác:

| Thành phần | Ai xử lý? | Tác dụng | Có xuất hiện trong `args[]`? |
| --- | --- | --- | --- |
| `-Xmx128m` | JVM/Java launcher | Cấu hình giới hạn heap tối đa | Không |
| `-Xms64m` | JVM/Java launcher | Cấu hình heap ban đầu | Không |
| `-Dstudy.mode=lab` | JVM/Java launcher | Đặt Java system property | Không |
| `-ea` | JVM/Java launcher | Bật kiểm tra `assert` | Không |
| `-cp out` | Java launcher | Chọn classpath tìm lớp/thư viện | Không |
| `ArgsBoundaryDemo` | Java launcher | Chọn lớp có điểm bắt đầu `main` | Không |
| `45` | Ứng dụng | Chuỗi đối số thứ nhất | Có: `args[0]` |
| `"Java core"` | Shell rồi ứng dụng | Một chuỗi chứa khoảng trắng | Có: `args[1]` |
| `--check` | Ứng dụng | Cờ do ứng dụng tự quy định | Có: `args[2]` |

`-cp` là **tùy chọn của launcher** chứ không phải phép đặt giới hạn bộ nhớ cho JVM. Còn `-D` tạo **system property**, không phải biến môi trường của hệ điều hành.

**Quy tắc thực hành:** các tùy chọn Java như `-Xmx`, `-D`, `-cp` phải đặt ở phần trước tên lớp đối với dạng chạy này; nội dung sau tên lớp được coi là dữ liệu ứng dụng.

## 2. Tạo chương trình minh họa để nhìn thấy `args[]`

Tạo tệp **`ArgsBoundaryDemo.java`** chứa mã Java sau:

~~~java
public class ArgsBoundaryDemo {
    public static void main(String[] args) {
        String mode = System.getProperty("study.mode", "default");

        System.out.println("study.mode=" + mode);
        System.out.println("args.length=" + args.length);

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "]=" + args[i]);
        }

        if (args.length > 0) {
            try {
                int minutes = Integer.parseInt(args[0]);
                if (minutes < 0) {
                    System.out.println("minutes=INVALID_NEGATIVE");
                } else {
                    System.out.println("minutes=" + minutes);
                }
            } catch (NumberFormatException ex) {
                System.out.println("minutes=INVALID_NUMBER");
            }
        }
    }
}
~~~

Ý nghĩa:

- `main(String[] args)` nhận **mảng chuỗi**. Dù bạn gõ `45`, trong `args[0]` ban đầu vẫn là `String` `"45"`, không phải số `int`.
- `System.getProperty("study.mode", "default")` đọc system property đã được cấu hình; nếu property chưa có thì dùng chuỗi mặc định `default`.
- Vòng `for` in **đúng từng chuỗi** nhận được và chỉ số của nó.
- `Integer.parseInt` minh họa việc ứng dụng tự phân tích đối số. Java launcher không tự chuyển mọi đối số ứng dụng thành số.
- Giá trị âm và chuỗi không phải số được xử lý tường minh; đó là **quy tắc ứng dụng**, không phải quy tắc của `-Xmx` hay `-D`.

Đây là chương trình Java độc lập, không cần thư viện bên ngoài, không cần framework hay tệp cấu hình đặc biệt.

## 3. Biên dịch và chạy trên Windows PowerShell hoặc Linux

Trước tiên kiểm tra JDK:

~~~bash
java -version
javac -version
~~~

Lưu `ArgsBoundaryDemo.java` trong một thư mục làm việc, mở terminal ở thư mục đó.

**Tạo thư mục đầu ra trên Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
~~~

**Tạo thư mục đầu ra trên Linux/Bash:**

~~~bash
mkdir -p out
~~~

Biên dịch — lệnh giống nhau ở cả hai hệ điều hành:

~~~bash
javac -encoding UTF-8 -d out ArgsBoundaryDemo.java
~~~

Sau đó chạy:

~~~bash
java -Xmx128m -Dstudy.mode=lab -cp out ArgsBoundaryDemo 45 "Java core" --check
~~~

**Kết quả dự kiến:**

~~~text
study.mode=lab
args.length=3
args[0]=45
args[1]=Java core
args[2]=--check
minutes=45
~~~

**Tại sao?**

1. Java launcher nhận `-Xmx128m` để yêu cầu cấu hình heap tối đa; tùy chọn này **không đi vào `args[]`**.
2. `-Dstudy.mode=lab` tạo property `study.mode` mang giá trị `lab`. Mã đọc nó qua `System.getProperty`.
3. `-cp out` chỉ thư mục tìm lớp `ArgsBoundaryDemo` đã được biên dịch.
4. `ArgsBoundaryDemo` xác định lớp được chạy.
5. Ba chuỗi còn lại đi vào `args[0]`, `args[1]` và `args[2]`. Dấu nháy quanh `"Java core"` được **shell** dùng để giữ hai từ thành **một đối số**, không phải ký tự thuộc nội dung chuỗi nhận được.

Không nên dựa vào con số bộ nhớ heap thực tế để kiểm chứng ví dụ: `-Xmx128m` quy định cấu hình giới hạn, không cam kết JVM cấp phát hoặc sử dụng đúng 128 MiB ngay khi chạy.

## 4. Đặt `-D` sai vị trí: kết quả thay đổi rõ rệt

Hãy so sánh hai lệnh có cùng văn bản `-Dstudy.mode=lab`:

**Đặt trước tên lớp — đây là tùy chọn Java:**

~~~bash
java -Dstudy.mode=lab -cp out ArgsBoundaryDemo 45
~~~

~~~text
study.mode=lab
args.length=1
args[0]=45
minutes=45
~~~

**Đặt sau tên lớp — đây là đối số chương trình:**

~~~bash
java -cp out ArgsBoundaryDemo 45 -Dstudy.mode=lab
~~~

~~~text
study.mode=default
args.length=2
args[0]=45
args[1]=-Dstudy.mode=lab
minutes=45
~~~

Lệnh thứ hai **không đặt system property** `study.mode`. Chuỗi bắt đầu bằng `-D` chỉ là một phần tử trong `args[]`, và vì ứng dụng ví dụ không tự phân tích chuỗi đó nên nó không thay đổi cách chạy.

Tương tự, chạy:

~~~bash
java -cp out ArgsBoundaryDemo 45 -Xmx128m
~~~

sẽ đưa chuỗi `-Xmx128m` vào đối số ứng dụng, **không đặt giới hạn heap qua chuỗi đó**. Tác dụng của ký tự `-` phụ thuộc **bộ phân tích lệnh nào đang đọc nó**.

Đây là nguyên nhân phổ biến của những lỗi kiểu “đã thêm `-D` mà ứng dụng vẫn đọc property mặc định”.

## 5. Đối số ứng dụng không tự có ý nghĩa

Java chỉ đưa các chuỗi sau lớp tới `main`. Chương trình phải **tự quyết định** chúng đại diện cho gì.

Giả sử một ứng dụng khác quy định:

~~~text
java App 15 --verbose --output=result.txt
~~~

`15` có thể là số lượng, số phút hay một mã tùy ý; `--verbose` có thể bật log; `--output=result.txt` có thể chọn tên tệp. **Đó là quy ước riêng của `App`**, không phải bộ tùy chọn chuẩn do JVM xử lý.

Trong chương trình `ArgsBoundaryDemo`:

- `45` được diễn giải thành số phút chỉ vì mã chủ động gọi `Integer.parseInt(args[0])`.
- `--check` được in ra nhưng chưa làm gì khác vì mã không có điều kiện xử lý nó.
- Khi không có đối số, `args.length = 0`; vòng lặp không in phần tử nào, và khối parse được bỏ qua.
- Khi `args[0]` là `abc` hoặc số vượt miền `int`, `parseInt` thất bại; chương trình in `minutes=INVALID_NUMBER`.
- Khi `args[0] = -5`, phép parse thành công nhưng ứng dụng báo `minutes=INVALID_NEGATIVE`.

Lỗi parse và dữ liệu âm là hai tình huống khác nhau: một tình huống **sai định dạng số**, tình huống còn lại **định dạng đúng nhưng vi phạm yêu cầu**.

## 6. `-D`, biến môi trường và classpath khác nhau thế nào?

Một hệ thống thường có cả **Java system properties**, **environment variables** và **program arguments**. Chúng không thay thế cho nhau.

| Cơ chế | Cách thiết lập / truyền | Cách Java đọc | Đặc điểm |
| --- | --- | --- | --- |
| System property | `java -Dstudy.mode=lab ...` | `System.getProperty("study.mode")` | Thuộc hệ thống properties của tiến trình JVM |
| Biến môi trường | Do shell/hệ điều hành đặt trước khi chạy | `System.getenv("STUDY_MODE")` | Được tiến trình thừa hưởng từ môi trường |
| Đối số chương trình | Sau tên lớp | `args[0]`, `args[1]`... | Mảng chuỗi ứng dụng nhận |
| Classpath | `java -cp out ...` | Được launcher/loader sử dụng | Xác định nơi tìm lớp và các thư viện |

Ví dụ thiết lập **biến môi trường** chỉ trong phiên terminal hiện tại:

**PowerShell:**

~~~powershell
$env:STUDY_MODE = "lab"
~~~

**Bash/Linux:**

~~~bash
export STUDY_MODE=lab
~~~

Nếu muốn thử trực tiếp trong mã, bổ sung lời gọi này vào `main`:

~~~java
System.out.println(
        "env.STUDY_MODE=" + System.getenv("STUDY_MODE"));
~~~

Đây là **đoạn bổ sung**, không có sẵn trong đầu ra chuẩn ở mục 3. Lệnh đặt biến môi trường `STUDY_MODE` không tự tạo Java system property `study.mode`; nếu muốn hỗ trợ cả hai, ứng dụng phải định nghĩa rõ quy tắc ưu tiên.

Lưu ý: classpath nhiều mục dùng ký tự phân tách **`;` trên Windows** và **`:` trên Linux/macOS**. Ví dụ ở bài này chỉ có một thư mục `out` nên cùng một lệnh `-cp out` hoạt động trên cả hai nền tảng.

## 7. Các cách khởi chạy khác vẫn có ranh giới tương tự

### Chạy JAR thực thi

Nếu đã có tệp JAR hợp lệ chứa cấu hình `Main-Class`, cú pháp điển hình là:

~~~bash
java -Xmx256m -Dstudy.mode=prod -jar app.jar 45 --check
~~~

- `-Xmx256m` và `-Dstudy.mode=prod`: tùy chọn JVM.
- `-jar app.jar`: Java launcher chọn JAR và main class được cấu hình trong manifest.
- `45`, `--check`: đối số ứng dụng được truyền đến `main`.

Đây chỉ là **ví dụ cú pháp**: bài này không tạo `app.jar`, nên không chạy lệnh trên nếu chưa có JAR tương ứng. Tên JAR không được truyền thành `args[0]`.

### Chạy thẳng tệp nguồn trên JDK 17+

Java cũng hỗ trợ chế độ chạy tệp nguồn:

~~~bash
java -Xmx128m -Dstudy.mode=lab ArgsBoundaryDemo.java 45 "Java core" --check
~~~

Trong cách này, `java` biên dịch mã nguồn trong bộ nhớ rồi chạy nó; không cần lệnh `javac` riêng. Tùy chọn JVM vẫn đi **trước tệp nguồn**; dữ liệu ứng dụng vẫn đi **sau tệp nguồn**.

Lệnh trên giả định bạn đang ở thư mục có `ArgsBoundaryDemo.java`. Nếu đã chỉ định đường dẫn khác, thay tên tệp bằng đường dẫn thực tế.

## 8. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `System.getProperty` trả `default` dù đã gõ `-D` | Đặt `-D` sau tên lớp, sai key hoặc chưa cấu hình | Đưa `-Dkey=value` lên trước lớp, kiểm tra chính tả |
| `args.length` khác số mong đợi | Đếm cả tên lớp hoặc chia nhầm chuỗi có khoảng trắng | Chỉ đếm chuỗi sau tên lớp; đặt chuỗi có khoảng trắng trong nháy kép |
| `-Xmx...` xuất hiện trong `args[]` | Đã đặt tùy chọn ở vị trí đối số ứng dụng | Đưa lên trước tên lớp hoặc tên tệp/JAR |
| JVM báo không nhận diện tùy chọn | Gõ sai flag hoặc phiên bản JDK không hỗ trợ | Kiểm tra `java -version` và `java --help` |
| Không tìm được main class | Thiếu `-cp out`, classpath sai hoặc chưa biên dịch | Xem tệp `.class` và kiểm tra tên lớp |
| `NumberFormatException` | Đối số được parse không phải số `int` hợp lệ | Kiểm tra chuỗi, miền số và thông báo |
| Heap hết bộ nhớ | Dữ liệu hoặc hành vi cấp phát vượt khả năng JVM | Đo/điều tra sử dụng bộ nhớ, không chỉ tăng `-Xmx` tùy tiện |

Muốn xem thêm các tùy chọn launcher:

~~~bash
java --help
java -X
~~~

Một số tùy chọn JVM chuyên sâu có dạng `-XX:...`; cú pháp và sự hỗ trợ phụ thuộc phiên bản/triển khai JVM. Không nên chép tùy chọn chuyên sâu từ môi trường khác mà chưa hiểu tác dụng.

### Đừng nhầm lỗi Java với lỗi của shell

Trước khi Java launcher đọc đối số, **shell** đã xử lý dấu nháy, khoảng trắng, biến môi trường và một số ký tự đặc biệt. PowerShell và Bash không có quy tắc hoàn toàn giống nhau. Ví dụ cách trích dẫn một đối số chứa khoảng trắng bằng `"Java core"` hoạt động trong cả hai, nhưng quy tắc escape các dấu nháy lồng nhau khác nhau.

Khi cần chẩn đoán, hãy bắt đầu bằng ví dụ đơn giản và in `args.length` cùng từng `args[i]` như chương trình trên. Đừng vội kết luận JVM đã làm mất một chuỗi nếu shell là bên đã phân tách nó khác dự kiến.

## 9. Bài tập tự kiểm tra

**Bài 1 — Dự đoán đầu ra.** Với:

~~~bash
java -Dstudy.mode=study -cp out ArgsBoundaryDemo 20 "bai mot"
~~~

Hãy dự đoán property, số đối số và giá trị từng đối số.

*Đáp án:* property `study`, `args.length=2`, `args[0]=20`, `args[1]=bai mot`, `minutes=20`.

**Bài 2 — Phát hiện đặt sai vị trí.**

~~~bash
java -cp out ArgsBoundaryDemo -Xmx256m 20
~~~

Ở đây giới hạn heap có được đặt bởi chuỗi `-Xmx256m` không? `args[]` chứa gì?

*Đáp án:* Không. `args[0]="-Xmx256m"`, `args[1]="20"`, ứng dụng in `minutes=INVALID_NUMBER` do cố parse phần tử đầu.

**Bài 3 — Phân biệt ba cơ chế.** Muốn ứng dụng đọc cấu hình `study.mode` qua `System.getProperty`, bạn nên dùng `-D`, biến môi trường hay `args[0]`?

*Đáp án:* Dùng `-Dstudy.mode=...` ở trước tên lớp. Hai cách kia chỉ có tác dụng nếu ứng dụng chủ động đọc và ánh xạ chúng.

**Bài 4 — Sửa câu lệnh chạy.** Chương trình cần nhận `45` và `--check` trong `args[]`, giới hạn heap được yêu cầu là `128m`, property `study.mode=qa`. Hãy viết một lệnh chạy đúng.

*Một đáp án:*

~~~bash
java -Xmx128m -Dstudy.mode=qa -cp out ArgsBoundaryDemo 45 --check
~~~

**Bài 5 — Thử dữ liệu lỗi.** Lần lượt đặt `args[0]` thành `-1`, `abc` và `2147483648`. Chúng khác nhau thế nào?

*Đáp án:* `-1` parse thành công nhưng vi phạm miền dữ liệu; `abc` không phải số; `2147483648` là số viết đúng hình thức thập phân nhưng vượt miền `int`, nên hai giá trị sau đều bị `NumberFormatException`.

## Checklist ghi nhớ

- [ ] Biết phân biệt **tùy chọn trước tên lớp/JAR/tệp nguồn** và **đối số sau điểm bắt đầu**.
- [ ] Biết `-Xmx` cấu hình heap, `-D` cấu hình system property, còn `-cp` là tùy chọn tìm lớp của launcher.
- [ ] Biết `String[] args` chỉ chứa những chuỗi mà ứng dụng được truyền sau entry point.
- [ ] Biết vì sao `"hai tu"` được truyền thành một đối số trên PowerShell/Bash.
- [ ] Biết `System.getProperty` và `System.getenv` đọc hai nguồn cấu hình khác nhau.
- [ ] Biết cách chạy `javac` rồi `java -cp out ...` trên cả Windows/Linux và so sánh với `java TenTep.java`.
- [ ] Có thể tự đọc `args.length`, phân loại lỗi parse và sửa vị trí `-D` khi cấu hình không có hiệu lực.

**Kết luận:** Hãy nhìn lệnh Java như hai phần: **cấu hình cách chạy Java** và **dữ liệu đưa cho ứng dụng**. Đặt đúng phía của ranh giới tên lớp/JAR/tệp nguồn giúp tránh nhầm lẫn giữa JVM, Java launcher và `main(String[] args)`.
