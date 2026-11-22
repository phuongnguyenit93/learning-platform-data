# Dùng tệp đối số @argfile cho tập nguồn lớn với javac

Khi dự án có vài tệp Java, ta có thể gọi trực tiếp `javac Main.java Helper.java`. Khi danh sách tăng lên hàng trăm hoặc hàng nghìn tệp, dòng lệnh trở nên khó quản lý, khó tái tạo và có thể chạm giới hạn độ dài của shell/hệ điều hành. `javac` hỗ trợ **tệp đối số** (command-line argument file, thường gọi `@argfile`): lưu các đối số trình biên dịch trong một tệp văn bản, rồi yêu cầu `javac` đọc và mở rộng nội dung tệp đó.

Bài này tập trung vào việc biên dịch **một tập nguồn Java lớn** bằng `javac`: cách viết và chạy argfile, kết hợp các tùy chọn, đường dẫn, các giới hạn cú pháp, tạo danh sách nguồn ổn định và xử lý lỗi. Các ví dụ dùng Java 17+.

## 1. Argfile là gì và khi nào nên dùng?

So sánh hai lệnh có cùng ý nghĩa nếu tệp `sources.args` chứa đúng ba đường dẫn nguồn:

~~~bash
javac -d out src/p/App.java src/p/Logic.java src/p/Validation.java
javac -d out @sources.args
~~~

Với cách thứ hai, `javac` gặp đối số bắt đầu bằng `@`, đọc tệp `sources.args` và **thay đối số đó bằng các token tìm được trong tệp**. Argfile không phải mã Java, không phải tập lệnh shell, không phải file `.class` hoặc `.jar`. Nó chỉ là văn bản mang các **đối số cho công cụ javac**.

Lợi ích trong thực tế:

- Tránh giới hạn độ dài dòng lệnh khi cần chỉ rõ rất nhiều tệp `.java`.
- Làm lệnh biên dịch gọn, dễ đọc, dễ dùng lại trong terminal hoặc CI.
- Tách danh sách nguồn khỏi bộ tùy chọn (phiên bản Java, thư mục đầu ra, classpath).
- Giúp biết chính xác các tệp đầu vào của một lượt biên dịch, nhất là khi ghi lại danh sách vào artifact chẩn đoán.

`@argfile` là tính năng của chương trình `javac`. Nó **không tự tìm kiếm tất cả tệp Java** trong dự án và không thay thế toàn bộ nhiệm vụ của Maven/Gradle về quản lý phụ thuộc, biên dịch tăng dần hay quy trình build. Nếu dự án đã được build tool quản lý, dùng build tool thông thường vẫn hợp lý; argfile đặc biệt hữu ích cho biên dịch thủ công, công cụ tự viết và bước kiểm chứng độc lập.

## 2. Cấu trúc một argfile

Giả sử từ thư mục gốc dự án có cấu trúc:

~~~text
project/
├── compile.args
├── src/
│   └── com/
│       └── example/
│           └── argfile/
│               ├── App.java
│               └── MathHelper.java
└── out/                     # Thư mục đầu ra tạo trước khi biên dịch
~~~

Tệp `compile.args` là văn bản thuần (không thêm dấu `@` vào nội dung). Ví dụ:

~~~text
-encoding
UTF-8
--release
17
-d
out
src/com/example/argfile/App.java
src/com/example/argfile/MathHelper.java
~~~

Cú pháp này tương đương với lệnh:

~~~bash
javac -encoding UTF-8 --release 17 -d out src/com/example/argfile/App.java src/com/example/argfile/MathHelper.java
~~~

Nhưng ta gọi ngắn hơn:

~~~bash
javac @compile.args
~~~

Mỗi dòng trong ví dụ chứa một token. `javac` cũng cho phép ngăn cách các đối số bằng **khoảng trắng** trong cùng dòng; xuống dòng chỉ là cách trình bày dễ kiểm tra. Một option có giá trị, như `-d out`, phải cung cấp đủ **hai token** (tên option và giá trị), dù được đặt cùng dòng hay hai dòng. Tên argfile không cần phần mở rộng `.args`: `sources.txt` hoặc `javac.options` cũng dùng được.

**Ý nghĩa các option trong ví dụ:**

| Đối số | Tác dụng |
| --- | --- |
| `-encoding UTF-8` | Đọc nội dung tệp nguồn `.java` với UTF-8 |
| `--release 17` | Kiểm tra ngôn ngữ và API được hỗ trợ ở Java 17, tạo bytecode tương ứng |
| `-d out` | Ghi các tệp `.class` vào thư mục `out`, dưới các thư mục package phù hợp |
| Các đường dẫn `.java` | Các tệp được biên dịch trong cùng lượt |

`--release 17` yêu cầu bản `javac` hỗ trợ release 17 (ví dụ JDK 17 hoặc JDK mới hơn còn hỗ trợ mục tiêu đó). `-encoding UTF-8` điều khiển **mã hóa nguồn Java**, không có nghĩa là tự động chuyển đổi hoặc sửa cách mã hóa của mọi tệp argfile.

## 3. Ví dụ chạy được: hai tệp nguồn, một lượt biên dịch

**Tệp `src/com/example/argfile/MathHelper.java`:**

~~~java
package com.example.argfile;

public final class MathHelper {
    private MathHelper() {
    }

    public static int add(int a, int b) {
        return a + b;
    }
}
~~~

**Tệp `src/com/example/argfile/App.java`:**

~~~java
package com.example.argfile;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Tong: " + MathHelper.add(3, 4));
    }
}
~~~

Giữ nguyên `compile.args` ở mục trước. Từ thư mục `project`, chuẩn bị thư mục đầu ra rồi biên dịch:

~~~bash
mkdir out
javac @compile.args
java -cp out com.example.argfile.App
~~~

Đầu ra chương trình:

~~~text
Tong: 7
~~~

Thư mục `out` chứa tối thiểu:

~~~text
out/
└── com/
    └── example/
        └── argfile/
            ├── App.class
            └── MathHelper.class
~~~

`javac` biên dịch **cả hai tệp trong cùng một invocation** và giải quyết tham chiếu `App` → `MathHelper`. Thứ tự liệt kê hai tệp nguồn không phải là thứ tự bắt buộc phải định nghĩa các lớp theo chiều phụ thuộc; compiler phân tích cả tập nguồn.

Lệnh `java -cp out com.example.argfile.App` là bước **chạy chương trình đã biên dịch**, không phải là đối số bên trong `compile.args`. Hãy dùng tên lớp đầy đủ gồm package và classpath trỏ đến gốc chứa cây package.

Ví dụ trên giả sử `mkdir out` được chạy một lần trong thư mục gốc (nếu `out` đã tồn tại thì không cần tạo lại). Trong các shell cụ thể, lệnh tạo thư mục khi đã tồn tại có thể báo lỗi; điều này không làm thay đổi cơ chế argfile.

## 4. Tách tập nguồn và tùy chọn thành nhiều argfile

Một argfile không bắt buộc chứa cả option và tên nguồn. Khi có nhiều môi trường build, tách thành hai tệp giúp thay tập nguồn mà vẫn giữ cấu hình compiler, hoặc thay cấu hình mà không sửa tập nguồn.

**Tệp `options.args`:**

~~~text
-encoding
UTF-8
--release
17
-g
-d
out
~~~

**Tệp `sources.args`:**

~~~text
src/com/example/argfile/MathHelper.java
src/com/example/argfile/App.java
~~~

Biên dịch:

~~~bash
javac @options.args @sources.args
~~~

Ở đây cả hai tệp đều được `javac` mở rộng thành đối số của **cùng một lệnh biên dịch**. `-g` yêu cầu sinh thông tin gỡ lỗi; nếu cần tối ưu kích thước hoặc thay chính sách debug, có thể chỉnh riêng tệp tùy chọn.

Có thể kết hợp đối số viết trực tiếp và đối số argfile, ví dụ:

~~~bash
javac -Xlint:all @options.args @sources.args
~~~

Lệnh này áp dụng thêm các cảnh báo thuộc `-Xlint:all` cho lượt biên dịch. Đối số bên ngoài và bên trong argfile đều được phân tích như đối số của `javac`; khi một cấu hình xuất hiện nhiều lần, hãy dựa vào quy tắc của **từng option** thay vì mặc định rằng compiler sẽ luôn ưu tiên giá trị nào đó. Giữ một nguồn thiết lập duy nhất cho mỗi option sẽ dễ kiểm soát hơn.

**Quan trọng:** Có thể đặt nhiều argfile cạnh nhau trên dòng lệnh, nhưng **không đặt `@sources.args` bên trong `options.args` để mở rộng lồng nhau**. Cơ chế đọc argfile của `javac` không hỗ trợ phân giải `@file` đệ quy.

## 5. Khoảng trắng, tên đường dẫn và thư mục làm việc

Trong argfile, khoảng trắng hoặc xuống dòng có thể kết thúc token. Khi **một tên tệp chứa dấu cách**, hãy dùng dấu nháy kép quanh toàn bộ đường dẫn:

~~~text
-d
out
"src/example files/First.java"
"src/example files/Second.java"
~~~

Các tên tệp trên chỉ là minh họa cú pháp đường dẫn có khoảng trắng; để biên dịch thực tế chúng phải tồn tại và chứa mã Java hợp lệ. Nếu bỏ nháy kép, `src/example` và `files/First.java` có thể bị hiểu thành các token khác nhau.

Quy tắc quan trọng: **đường dẫn tương đối nằm bên trong argfile được giải quyết theo thư mục làm việc hiện tại của tiến trình `javac`, không theo thư mục đang chứa argfile.** Ví dụ:

~~~text
project/
├── config/
│   └── sources.args
└── src/
    └── p/
        └── App.java
~~~

Nếu đang ở `project` và tệp `config/sources.args` chứa `src/p/App.java`, gọi:

~~~bash
javac -d out @config/sources.args
~~~

sẽ dùng đường dẫn `project/src/p/App.java` (giả sử đã tạo `out`). Nó **không** tự chuyển thành `project/config/src/p/App.java`.

Nếu đổi thư mục làm việc rồi chạy cùng argfile, các đường dẫn tương đối bên trong có thể sai. Để pipeline ổn định, đặt working directory rõ ràng trước khi gọi compiler hoặc dùng đường dẫn tuyệt đối do công cụ build tạo ra.

Dấu phân cách đường dẫn cho `-cp` / `--class-path` cũng phụ thuộc hệ điều hành: dấu chấm phẩy `;` trên Windows, dấu hai chấm `:` trên Linux/macOS. Chẳng hạn:

~~~text
-cp
"libs/core.jar;libs/util.jar"
~~~

là ví dụ cho **Windows**. Trên Linux/macOS, thay dấu `;` bằng `:`. Nháy kép bảo vệ một giá trị chứa khoảng trắng (nếu có); nó không làm thay đổi dấu phân cách classpath của hệ điều hành.

## 6. Argfile không phải shell script: giới hạn phải nhớ

Một số thói quen thường dùng trong terminal không tự hoạt động trong tệp `@argfile` của `javac`:

1. **Không mở rộng wildcard**: dòng `src/*.java` bên trong argfile không có nghĩa là “tất cả tệp Java trong src”. Phải ghi các tên tệp nguồn thực tế, hoặc dùng công cụ sinh danh sách trước.
2. **Không có mở rộng `@file` lồng nhau**: để ghép argfile, liệt kê nhiều `@file` trực tiếp trên lời gọi `javac`.
3. **Không đặt option `-J` trong argfile**: `-J` truyền option tới JVM chạy compiler và được launcher xử lý riêng. Nếu cần, đặt bên ngoài, ví dụ `javac -J-Xmx1g @compile.args`.
4. **Không đặt lệnh shell trong argfile**: `cd`, `find`, `mkdir`, pipe, redirect hay phép thay thế biến môi trường của shell không trở thành thao tác shell chỉ vì xuất hiện trong argfile.
5. **Không coi argfile là cơ chế quản lý phụ thuộc**: `javac` vẫn cần `-cp`, `--module-path`, source path hoặc các đầu vào thích hợp khi dùng thư viện và module.
6. **Không coi argfile của `javac` và `java` là một tệp cấu hình có thể dùng thay thế mọi tình huống**: trình biên dịch và launcher có mục đích, option và cách xử lý riêng.

Vì vậy, tệp nguồn nhiều không nên được mô tả mơ hồ bằng:

~~~text
src/**/*.java
~~~

Cách đúng là cung cấp một tập đường dẫn thực, ví dụ:

~~~text
src/p/A.java
src/p/B.java
src/p/C.java
~~~

Sau khi có danh sách, `javac` xử lý chúng trong một lần gọi. Điều này cũng giúp phát hiện tình huống quên đưa một tệp vào tập nguồn thay vì tưởng rằng compiler tự quét toàn bộ dự án.

## 7. Sinh danh sách nguồn khi dự án lớn

Viết thủ công từng tên tệp có thể phù hợp với ví dụ nhỏ; với hàng trăm tệp, có thể sinh tệp `sources.args` bằng script rồi kiểm tra trước khi gọi `javac`. Script dưới đây là **công cụ hỗ trợ tạo argfile**, không phải một phần của cú pháp argfile.

Ví dụ Python 3 chạy từ **thư mục gốc dự án**:

~~~python
from pathlib import Path

source_root = Path("src")
source_files = sorted(path for path in source_root.rglob("*.java") if path.is_file())

if not source_files:
    raise SystemExit("Khong tim thay tep .java trong src")

def as_argument(path: Path) -> str:
    value = path.as_posix()
    if '"' in value or "\n" in value or "\r" in value:
        raise ValueError(f"Ten tep khong duoc ho tro trong vi du nay: {value!r}")
    return f'"{value}"'

Path("sources.args").write_text(
    "\n".join(as_argument(path) for path in source_files) + "\n",
    encoding="utf-8",
)
print(f"Da ghi {len(source_files)} tep vao sources.args")
~~~

Lưu chương trình thành `make_sources.py` rồi chạy:

~~~bash
python3 make_sources.py
javac @options.args @sources.args
~~~

Trên Windows, lệnh Python có thể là `python` hoặc `py` tùy cách cài đặt. Script cố ý:

- Duyệt file `.java` trong `src` và sắp xếp đường dẫn để **kết quả ổn định** giữa các lần chạy với cùng một cây nguồn.
- Quấn mỗi đường dẫn bằng nháy kép để xử lý tên thư mục có khoảng trắng.
- Báo lỗi khi đường dẫn chứa nháy kép hoặc ký tự xuống dòng, nhằm tránh sinh ra danh sách token khó kiểm soát.
- Dừng khi không tìm thấy tệp để tránh chạy compiler trên tập nguồn rỗng ngoài ý muốn.

Đây là minh họa cho **đường dẫn thông thường**. Nếu đường dẫn chứa ký tự đặc biệt của quy tắc escape ở môi trường cụ thể, cần kiểm tra và điều chỉnh cách mã hóa/escape; các đường dẫn do script xuất ra phải được xác nhận đúng trước khi dùng. Việc script ghi UTF-8 không thay thế kiểm tra mã hóa mà bản `javac`/môi trường đang dùng đọc cho tệp đối số. Với môi trường hạn chế mã hóa, nên ưu tiên đường dẫn ASCII hoặc kiểm chứng bằng một lượt biên dịch thực tế.

Trong dự án Gradle/Maven, nên dùng cách thu thập nguồn do build tool hỗ trợ thay vì duy trì hai danh sách nguồn độc lập; ví dụ script phù hợp nhất cho biên dịch `javac` thủ công hoặc tác vụ chẩn đoán.

## 8. Kết hợp với classpath và thư viện ngoài

Giả sử mã nguồn dùng thư viện đã biên dịch thành `libs/example-api.jar`. Ngoài các tệp nguồn, `javac` phải tìm được lớp thư viện trong thời gian biên dịch. Có thể đưa vào `options.args`:

~~~text
-encoding
UTF-8
--release
17
-d
out
-cp
libs/example-api.jar
~~~

Sau đó:

~~~bash
javac @options.args @sources.args
~~~

**Tập nguồn** và **classpath** phục vụ hai việc khác nhau:

| Thành phần | Vai trò |
| --- | --- |
| `sources.args` | Chỉ ra các tệp `.java` được biên dịch trực tiếp |
| `-cp libs/example-api.jar` | Chỉ ra thư viện đã có bytecode để compiler phân giải kiểu |
| `-d out` | Chỉ ra nơi ghi kết quả `.class` |
| `java -cp ...` | Thiết lập classpath **lúc chạy**, độc lập với lời gọi `javac` |

Nếu mã thực sự dùng thư viện đó khi chạy, classpath runtime cũng phải có thư viện; riêng việc xuất hiện trong argfile của `javac` không tự đưa JAR vào classpath của `java`. Trên Linux/macOS, ví dụ chạy có thể là `java -cp out:libs/example-api.jar p.Main`; trên Windows dùng `out;libs/example-api.jar`. Tên `p.Main` chỉ là ví dụ; hãy dùng lớp có `main` thật trong dự án.

Với dự án Java module (JPMS), classpath khác module path. Có thể đặt các option như `--module-path`, `--module-source-path` hay `-d` trong argfile **nếu hợp với cấu trúc dự án**. Việc dùng `@argfile` chỉ đổi cách cung cấp tham số, không thay đổi quy tắc module, `requires`, `exports` và đường dẫn biên dịch.

## 9. Đối chiếu với các cách truyền tên tệp khác

| Cách gọi | Điểm mạnh | Điểm cần chú ý |
| --- | --- | --- |
| `javac A.java B.java` | Nhanh, rõ ràng khi rất ít tệp | Dòng lệnh dài khi số tệp lớn |
| `javac @sources.args` | Danh sách nguồn dễ lưu, đọc và tái sử dụng | Phải tạo và duy trì tệp đối số hợp lệ |
| `javac @options.args @sources.args` | Tách chính sách compiler khỏi tập nguồn | Không được dùng `@file` lồng trong file khác |
| Build bằng Gradle/Maven | Quản lý vòng đời, phụ thuộc, thay đổi tăng dần tùy cấu hình | Phải hiểu cấu hình build của dự án |

Nếu chỉ muốn biên dịch thử một lớp, một lệnh `javac` trực tiếp có thể dễ hiểu hơn. Nếu cần biên dịch lại hàng trăm nguồn với cùng cấu hình, argfile giúp giảm thao tác và sai sót. Nếu cần build cả hệ thống nhiều module, kiểm thử, package, tải phụ thuộc và cache, build tool thường là lựa chọn thích hợp hơn.

## 10. Lỗi thường gặp và cách chẩn đoán

**Lỗi 1 — `javac` không tìm được tệp nguồn.**

Ví dụ, trong `sources.args` ghi `src/app/Main.java` nhưng terminal đang ở một thư mục khác. Kiểm tra working directory, đường dẫn có thực sự tồn tại và có phải đường dẫn tương đối theo nơi chạy compiler không. Đừng tự gắn đường dẫn với thư mục chứa argfile.

**Lỗi 2 — Một đường dẫn có khoảng trắng bị tách.**

Ghi `src/my code/App.java` không có nháy kép sẽ tạo nhiều token. Sửa thành `"src/my code/App.java"` trong argfile. Dấu nháy kép dùng để nhóm thành một đối số; không nên đưa chúng thành ký tự thực trong tên tệp.

**Lỗi 3 — Dùng `*.java` trong argfile.**

`javac` không mở rộng wildcard trong danh sách argfile. Sinh danh sách tệp cụ thể như mục 7 rồi kiểm tra tệp được ghi. Việc shell có thể mở rộng glob ở **dòng lệnh trực tiếp** trên một số hệ không có nghĩa argfile cũng làm vậy.

**Lỗi 4 — Chèn `@other.args` vào argfile.**

`javac` không mở rộng argfile đệ quy. Gọi `javac @options.args @sources.args` thay vì đặt `@sources.args` trong nội dung `options.args`.

**Lỗi 5 — Đặt `-J-Xmx1g` trong argfile.**

`-J` là tùy chọn của launcher dành cho JVM chạy compiler. Đặt nó ngoài file: `javac -J-Xmx1g @compile.args`.

**Lỗi 6 — `cannot find symbol`, `package ... does not exist`.**

Kiểm tra các tệp nguồn phụ thuộc đã có trong danh sách chưa, tên package có đúng không, `-cp`/`--module-path` có chứa dependency hợp lệ không. Đừng quy mọi lỗi phân giải kiểu về cú pháp `@argfile`: nếu compiler đã đọc argfile thành công, nguyên nhân có thể nằm trong cấu hình hoặc mã Java.

**Lỗi 7 — Lệnh biên dịch thành công nhưng `java` không tìm được main class.**

`javac` ghi file vào thư mục `-d`, còn `java` phải có `-cp`/module path và tên lớp chính thích hợp. Ví dụ ở mục 3 chạy `java -cp out com.example.argfile.App`.

**Lỗi 8 — Argfile chạy được ở máy này nhưng sai ở máy khác.**

Kiểm tra working directory, phân cách classpath theo OS, cách biểu diễn/đọc ký tự trong argfile, đường dẫn chứa khoảng trắng và phiên bản JDK. Hãy cố định điều kiện chạy CI và thử một ví dụ nhỏ trước khi mở rộng sang hàng nghìn nguồn.

## 11. Quy trình an toàn và dễ tái lập cho tập nguồn lớn

Một trình tự thực hành hữu ích:

1. **Chốt thư mục gốc dự án**: gọi mọi lệnh từ một working directory được ghi rõ.
2. **Tạo danh sách nguồn có thứ tự ổn định**: kiểm tra các tệp tồn tại, tránh trùng lặp, không dựa vào wildcard bên trong argfile.
3. **Tạo tệp tùy chọn riêng**: chỉ định `--release`, `-encoding`, `-d` và classpath/module path phù hợp.
4. **Kiểm tra nội dung argfile**: đường dẫn có khoảng trắng phải được quote; không chèn lệnh shell, `-J`, `@file` lồng hoặc option không được hỗ trợ.
5. **Tạo thư mục đầu ra** nếu cần rồi chạy `javac @options.args @sources.args`.
6. **Quan sát mã thoát và thông báo lỗi**. Nếu biên dịch thất bại, sửa nguồn/cấu hình; đừng giả định mọi lỗi đều do danh sách nguồn.
7. **Kiểm tra đầu ra** trong thư mục `-d` và chạy chương trình bằng classpath/module path runtime chính xác.

Có thể dùng `javac -version` để xác nhận compiler đang sử dụng, lưu lại `options.args` và `sources.args` phục vụ tái lập một lỗi build. Với danh sách sinh động từ mã nguồn thay đổi, tái tạo argfile trước mỗi lượt biên dịch; nếu danh sách cũ bỏ sót tệp mới, compiler sẽ không tự biết ý định “biên dịch toàn bộ cây nguồn”.

## 12. Tự kiểm tra kiến thức

**Câu 1.** Tệp `sources.args` nằm trong thư mục `config`, bên trong ghi `src/p/A.java`. Chạy `javac @config/sources.args` từ thư mục gốc `project`. Đường dẫn được hiểu ở đâu?

**Đáp án:** `project/src/p/A.java`, vì đường dẫn tương đối trong argfile được tính từ working directory của `javac`.

**Câu 2.** `sources.args` chứa:

~~~text
src/p/*.java
~~~

Liệu `javac @sources.args` có tự quét mọi tệp `.java` trong `src/p` không?

**Đáp án:** Không. Wildcard không được mở rộng trong argfile; cần liệt kê tên tệp thực.

**Câu 3.** Có `options.args` và `sources.args`. Có thể đặt dòng `@sources.args` vào bên trong `options.args` không?

**Đáp án:** Không dùng cách lồng này; chạy `javac @options.args @sources.args`.

**Câu 4.** `-encoding UTF-8` trong argfile dùng để làm gì?

**Đáp án:** Chỉ định encoding khi `javac` đọc các tệp **nguồn Java**. Nó không phải phép đảm bảo tự động về cách các công cụ khác tạo hoặc mã hóa tệp argfile.

**Câu 5.** Tại sao biên dịch thành công rồi chạy `java com.example.argfile.App` vẫn có thể lỗi?

**Đáp án:** Vì khi lớp ở `out`, launcher cần classpath phù hợp, ví dụ `java -cp out com.example.argfile.App`. Nội dung argfile của compiler không cấu hình runtime thay cho lệnh `java`.

## Ghi nhớ

`@argfile` là một cách **đưa danh sách đối số dài vào `javac`**, đặc biệt hữu ích khi tập nguồn lớn. Nội dung có thể gồm cả tùy chọn và tên tệp, nhưng đường dẫn tương đối phải theo working directory, các đường dẫn chứa khoảng trắng phải quote, wildcard và mở rộng lồng nhau không được hỗ trợ, và `-J` phải nằm ngoài argfile. Khi nắm rõ những giới hạn đó, một lệnh ngắn như `javac @options.args @sources.args` có thể thay thế một lệnh biên dịch dài mà vẫn giữ cùng ý nghĩa kỹ thuật.