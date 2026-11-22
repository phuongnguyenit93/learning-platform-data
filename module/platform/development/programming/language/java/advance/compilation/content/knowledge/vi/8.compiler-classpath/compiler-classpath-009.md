# Cô lập đầu ra và tránh tệp class cũ che lỗi thiếu phụ thuộc

## Mục tiêu học tập

Khi kết thúc bài, bạn có thể:

- Giải thích vì sao một lệnh `javac` có thể biên dịch thành công nhờ một file `.class` cũ, mặc dù bộ mã nguồn hoặc dependency được khai báo cho lần build hiện tại không đầy đủ.
- Phân biệt **source path**, **compiler classpath**, **thư mục đầu ra** và **runtime classpath**.
- Tái hiện tình huống “máy tôi build được, môi trường sạch lại lỗi” bằng ví dụ Java 17+ có thể chạy từ terminal.
- Dùng thư mục output riêng cho từng bước/module, xây dựng lại từ đầu trong một thư mục mới và xác minh đúng các artifact được dùng.
- Nhận biết khi nào `javac` báo lỗi thiếu symbol, khi nào chương trình biên dịch được nhưng JVM gặp lỗi liên kết/nạp lớp ở runtime.
- Xây dựng checklist tránh **stale class files** trong quy trình thủ công hoặc Gradle/Maven/CI.

Phạm vi bài là **classpath và tính đáng tin cậy của kết quả biên dịch**. Không cần framework hoặc IDE để thực hành.

## 1. Vì sao một tệp `.class` cũ có thể nguy hiểm?

Hãy tưởng tượng trước đây project có hai lớp:

- `dep.Greeter` cung cấp chức năng của một thư viện nội bộ.
- `app.Main` sử dụng `dep.Greeter`.

Ở lần build đầu, bạn biên dịch cả hai vào `build/classes`. Sau đó, tập source mà bạn **muốn** đưa vào lần build mới chỉ còn `app.Main`; dependency `dep.Greeter` chưa được khai báo hoặc chưa được build trong đầu vào dự kiến.

Nếu chạy:

~~~bash
javac -cp build/classes -d build/classes src/app/Main.java
~~~

`javac` vẫn tìm thấy `build/classes/dep/Greeter.class` được tạo trước đó. Compiler vì thế có thể kiểm tra thành công lời gọi tới `Greeter` dù **không có nguồn/thư viện Greeter trong tập đầu vào mới mà bạn muốn kiểm chứng**.

Điều này dẫn tới kết luận sai: “Tôi đã kiểm tra rằng project build độc lập được”. Thực tế bạn mới chứng minh rằng mã biên dịch được **trong môi trường còn artifact cũ**.

Một lần biên dịch vào **output mới hoàn toàn**, với classpath chỉ chứa dependency được phép, sẽ làm lỗi thiếu dependency lộ ra.

### 1.1 Cơ chế từng bước

~~~text
Lần 1: build cũ
src/dep/Greeter.java ─┐
                       ├─ javac -d build/classes ─> build/classes/dep/Greeter.class
src/app/Main.java ────┘                       └──> build/classes/app/Main.class

Lần 2: chỉ định biên dịch Main.java
                                      +----------------------------------+
javac -cp build/classes ... ---------->| classpath có Greeter.class cũ     |
                                      | compiler resolve dep.Greeter OK  |
                                      +----------------------------------+
                                                     |
                                                     v
                                      Kết quả "compile successful"
                                      nhưng phụ thuộc dự kiến còn thiếu

Lần 3: build trong output sạch
javac -cp build/clean -d build/clean src/app/Main.java
                                                     |
                                                     v
                                       package dep does not exist
                                       / cannot find symbol
~~~

**Không phải compiler bỏ qua lỗi.** Compiler kiểm tra đúng theo những class mà bạn cho phép nó thấy trên classpath. Vấn đề là **classpath chứa đầu vào ngoài ý định**.

Trong công việc thật, class cũ có thể sót do đổi tên/xóa source, chuyển package, thay đổi dependency, bỏ một module khỏi build, hoặc build từng phần nhưng giữ nguyên thư mục output.

## 2. Phân biệt bốn đường dẫn liên quan

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **Source files** | `src/app/Main.java` | Những file source bạn yêu cầu compiler xử lý |
| **Compile classpath** | `javac -cp build/lib ...` | Nơi `javac` tìm các lớp/thư viện đã biên dịch cần để kiểm tra source |
| **Output directory** | `javac -d build/app ...` | Thư mục nhận class file mà lệnh compile đang tạo |
| **Runtime classpath** | `java -cp build/app:build/lib app.Main` trên Linux/macOS | Nơi JVM tìm những class khi chạy chương trình |

Điểm quan trọng:

- `-d` **không đồng nghĩa** với `-cp`. `-d` xác định nơi ghi; `-cp` xác định nơi đọc các dependency đã biên dịch.
- Nếu bạn đưa cùng thư mục output cũ vào `-cp`, chính nó có thể trở thành **đầu vào** của lần compile tiếp theo.
- `javac` thường biên dịch các source được chỉ định, đồng thời có cơ chế tìm source/class liên quan theo source path và classpath. Vì thế cần kiểm soát cả các đường tìm kiếm, không chỉ nhìn danh sách file được ghi trên command line.
- Runtime classpath có thể khác compile classpath. Có thư viện khi biên dịch chưa chắc thư viện đó hiện diện khi chạy.
- Đường dẫn `src/` và `build/` trong ví dụ là quy ước dự án tự đặt; bản thân JVM không bắt buộc tên này.

### 2.1 Cơ chế tìm kiếm source ngầm của `javac`

Nếu một lớp đang được tham chiếu không được truyền trực tiếp như source, `javac` có thể tìm class file hoặc source file theo các đường tìm kiếm được cấu hình. Mặc định của source path và sự kết hợp với classpath phụ thuộc lựa chọn compile; do đó, lỗi “build vẫn được” có thể xuất phát từ **source được tìm ngầm** hoặc từ **class file cũ**.

Ở bài này, các lệnh dùng `-cp` rõ ràng và mỗi source được đặt ở thư mục riêng. Nhờ vậy, thí nghiệm cho thấy chính class file cũ là dependency làm lần biên dịch thành công. Với một pipeline phức tạp, nên cấu hình cả `-sourcepath` khi cần kiểm soát source discovery.

Tùy chọn `-implicit:none` điều khiển việc **sinh class file** cho những source được compiler tìm ngầm, nhưng nó **không tự xóa class cũ và không làm một classpath bẩn trở nên sạch**. Đừng dùng `-implicit:none` như giải pháp thay cho việc cô lập đầu vào.

## 3. Chuẩn bị ví dụ Java 17+ tái hiện lỗi

Cần một JDK 17 trở lên và terminal. Kiểm tra:

~~~bash
javac -version
java -version
~~~

Chương trình dùng hai file Java độc lập theo package:

~~~text
classpath-isolation-demo/
├── src/
│   ├── dep/
│   │   └── Greeter.java
│   └── app/
│       └── Main.java
└── build/
    └── ... (sẽ được tạo khi làm bài)
~~~

Tạo project mới và hai thư mục `src/dep`, `src/app` bằng trình quản lý file hoặc lệnh tạo thư mục của hệ điều hành. Mở terminal tại thư mục gốc `classpath-isolation-demo`.

### 3.1 Source thư viện: `src/dep/Greeter.java`

~~~java
package dep;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "Hello from Greeter";
    }
}
~~~

Phương thức `message()` là `static` và trả chuỗi cố định. Class nằm trong package `dep`; sau biên dịch sẽ tương ứng đường dẫn `dep/Greeter.class` dưới classpath root.

### 3.2 Source ứng dụng: `src/app/Main.java`

~~~java
package app;

import dep.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println("App: " + Greeter.message());
    }
}
~~~

`app.Main` cần `dep.Greeter` để biên dịch lời gọi `Greeter.message()`. Import giúp viết ngắn tên lớp trong source, nhưng `import` **không tự đưa JAR hoặc class file vào classpath**.

### 3.3 Tạo các thư mục output

Trong **PowerShell**, từ thư mục project:

~~~powershell
New-Item -ItemType Directory -Force build/classes, build/clean, build/lib, build/app | Out-Null
~~~

Trong **Bash/Zsh**:

~~~bash
mkdir -p build/classes build/clean build/lib build/app
~~~

Cần tạo hoặc xác minh thư mục nhận output trước lệnh `javac -d`. Bài dùng bốn thư mục khác nhau để quan sát rõ class nào sinh ở lần nào, tránh vô tình ghi đè artifact của một phép thử khác.

## 4. Thí nghiệm A: biên dịch cũ che lỗi thiếu dependency

### Bước A1 — Biên dịch cả thư viện và ứng dụng vào thư mục dùng chung

~~~bash
javac -encoding UTF-8 -d build/classes src/dep/Greeter.java src/app/Main.java
java -cp build/classes app.Main
~~~

Stdout khi chạy:

~~~text
App: Hello from Greeter
~~~

Sau compile, thư mục `build/classes` chứa:

~~~text
build/classes/
├── dep/
│   └── Greeter.class
└── app/
    └── Main.class
~~~

Cả hai class hợp lệ, và classpath runtime chứa cùng root `build/classes` nên JVM tìm được chúng.

### Bước A2 — Giả lập lần compile chỉ có source ứng dụng

Bây giờ giả sử pipeline mới **chỉ được phép build ứng dụng**, còn dependency của `dep.Greeter` bị bỏ sót ở cấu hình mới. Ta cố ý **không đưa** `src/dep/Greeter.java` vào danh sách file biên dịch, nhưng lại dùng classpath chứa đầu ra của lần trước:

~~~bash
javac -encoding UTF-8 -cp build/classes -d build/classes src/app/Main.java
~~~

Lệnh này vẫn biên dịch thành công. `Main.java` nhìn thấy `dep.Greeter` thông qua **`build/classes/dep/Greeter.class`**, class file cũ vẫn tồn tại từ bước A1.

Điều kiện làm sai kết luận ở đây không phải `Greeter.java` bị xóa khỏi máy. Ngay cả khi source còn nằm ở `src/dep`, nó **không thuộc tập source/dependency dự kiến của bước A2**. Classpath đã vô tình mang phần phụ thuộc vào phép kiểm tra.

Bạn có thể nghĩ “không có lỗi nên dependency đầy đủ”, nhưng một build từ trạng thái hoàn toàn mới chưa chắc lặp lại kết quả này.

### Bước A3 — Biên dịch vào output sạch để kiểm tra độc lập

Vẫn từ source `src/app/Main.java`, nhưng không để classpath nhìn thấy `build/classes`:

~~~bash
javac -encoding UTF-8 -cp build/clean -d build/clean src/app/Main.java
~~~

Thí nghiệm dùng `build/clean` vốn vừa được tạo nhưng **chưa chứa class file nào**. Không có `dep.Greeter` trên classpath của lệnh compile này; vì thế compiler sẽ báo lỗi. Chẩn đoán có thể gồm những dòng như:

~~~text
package dep does not exist
cannot find symbol
~~~

Số dòng, dấu mũ định vị và cách sắp xếp diagnostic có thể khác theo phiên bản JDK. Điểm cần xác minh là **exit code khác 0** và compiler không tạo một bản `app.Main` hợp lệ từ lần compile đó.

Vì sao `javac` không tự lấy `src/dep/Greeter.java`? Bởi trong lệnh A3 ta chỉ truyền file `src/app/Main.java` và đặt compile classpath rõ ràng là `build/clean`. Source của `dep.Greeter` ở đường dẫn khác và không được đưa vào nguồn mà compiler đang tìm.

### Bước A4 — Sửa đúng bằng cách khai báo dependency trong lần build sạch

Nếu cả hai source được phép thuộc cùng một output/module, truyền cả hai source:

~~~bash
javac -encoding UTF-8 -d build/clean src/dep/Greeter.java src/app/Main.java
java -cp build/clean app.Main
~~~

Stdout:

~~~text
App: Hello from Greeter
~~~

Bản build sạch nay thành công vì **đầu vào thực sự đầy đủ**. Nếu hai phần là hai module/thư viện độc lập, hãy làm như thí nghiệm B dưới đây: biên dịch thư viện riêng rồi đưa output của thư viện vào compile classpath của ứng dụng.

### Điều đã được chứng minh

- **A2 thành công:** chỉ chứng minh `Main.java` biên dịch được khi nhìn thấy `Greeter.class` cũ.
- **A3 thất bại:** chứng minh tập đầu vào sạch chỉ chứa `Main.java` không đủ để biên dịch ứng dụng.
- **A4 thành công:** chứng minh khi bổ sung dependency thực sự, bản build sạch hoạt động.

Đây là bằng chứng có thể lặp lại về cách stale artifact che lỗi thiếu phụ thuộc. Đừng diễn giải thành lỗi xác minh kiểu của `javac`: compiler luôn xem những class nằm trên classpath đã chỉ định là nguồn thông tin hợp lệ.

## 5. Thí nghiệm B: cô lập output theo module

Trong dự án có nhiều module, một cách rõ ràng là mỗi module có output riêng:

~~~text
build/
├── lib/
│   └── dep/Greeter.class
└── app/
    └── app/Main.class
~~~

### Bước B1 — Build thư viện

~~~bash
javac -encoding UTF-8 -d build/lib src/dep/Greeter.java
~~~

Lúc này `build/lib` chứa `dep/Greeter.class`. Đây là artifact thư viện được phép dùng làm dependency khi biên dịch ứng dụng.

### Bước B2 — Build ứng dụng với dependency khai báo tường minh

~~~bash
javac -encoding UTF-8 -cp build/lib -d build/app src/app/Main.java
~~~

Ở đây:

- `-cp build/lib` chỉ cho compiler nơi tìm `dep.Greeter`.
- `-d build/app` ghi **duy nhất class do lần biên dịch ứng dụng sinh** vào output ứng dụng.
- Không cần trộn `Greeter.class` vào `build/app`.
- Việc phân tách làm cho thiếu dependency dễ phát hiện hơn và giúp truy nguồn từng artifact.

### Bước B3 — Runtime classpath phải chứa cả hai phần

Trên **Linux/macOS**:

~~~bash
java -cp "build/app:build/lib" app.Main
~~~

Trên **Windows (PowerShell/CMD)**:

~~~powershell
java -cp "build/app;build/lib" app.Main
~~~

Stdout của cả hai:

~~~text
App: Hello from Greeter
~~~

Dấu phân cách nhiều entry của classpath là dấu **`:` trên Linux/macOS** và **`;` trên Windows**. Trên cả hai hệ điều hành, package vẫn có tên `app.Main` và `dep.Greeter`; không thay tên package bằng slash hoặc backslash khi chạy.

### Bước B4 — Biên dịch được nhưng chạy thiếu dependency

Chạy ứng dụng chỉ với output ứng dụng:

~~~bash
java -cp build/app app.Main
~~~

JVM có thể tìm thấy `app.Main`, nhưng khi đi đến lời gọi `Greeter.message()`, lớp `dep.Greeter` không nằm trong runtime classpath. Với ví dụ này, lỗi thường là `NoClassDefFoundError: dep/Greeter`, thường kèm nguyên nhân như `ClassNotFoundException` từ class loader. Phần stack trace chi tiết phụ thuộc JVM, nên không dùng nó làm output cố định.

Bài học là **compile classpath và runtime classpath phục vụ hai thời điểm khác nhau**. Một class có thể hiện diện trong bước compile mà vắng mặt trong bước chạy. Lỗi đó khác với trường hợp A3, nơi compiler không tìm được symbol ngay từ đầu.

### Bước B5 — Tránh vô tình dùng output của application làm dependency

Khi biên dịch ứng dụng, lựa chọn:

~~~bash
javac -cp build/lib -d build/app src/app/Main.java
~~~

rõ ràng hơn việc đưa một thư mục tổng hợp còn chứa hàng loạt class cũ vào `-cp`. Trong một project lớn, mỗi module nên có output riêng, và dependency phải được mô tả bằng dependency graph hoặc entry cụ thể.

Cô lập output không phải bảo đảm tuyệt đối: nếu bạn vẫn tham chiếu tới JAR sai version hoặc một thư mục bị ô nhiễm, build vẫn có thể cho kết quả sai. Cần kết hợp **đúng tập đầu vào**, **đúng dependency version** và **bằng chứng clean build**.

## 6. Những tình huống thực tế tạo stale class file

### 6.1 Xóa hoặc đổi tên source nhưng class file cũ còn lại

Trước đây project có `src/dep/Legacy.java` và `build/classes/dep/Legacy.class`. Sau khi source bị xóa hoặc chuyển sang `NewApi.java`, nếu quy trình compile chỉ viết class mới mà **không dọn output cũ**, `Legacy.class` có thể vẫn tồn tại.

Nếu một source khác tham chiếu `dep.Legacy` và compiler classpath trỏ tới output cũ, build có thể vẫn qua dù source `Legacy.java` đã biến mất. Khi đóng gói từ toàn bộ output cũ, artifact không mong muốn còn có thể lọt vào JAR.

Một cách kiểm chứng là so sánh danh sách class của output sau build sạch với output incremental; nếu thấy những class không còn source/dependency hợp lệ, cần xem lại cleanup hoặc lifecycle của build.

### 6.2 Chuyển package

Đổi `package old;` thành `package newer;` làm compiler sinh class ở đường dẫn khác. Nếu `old/Thing.class` không bị dọn, các chỗ vẫn import `old.Thing` có thể tiếp tục compile từ binary cũ.

Không nên nghĩ đổi package trong source sẽ tự động xóa class thuộc package cũ trong mọi script tự viết. Việc xóa obsolete outputs thuộc trách nhiệm của build process.

### 6.3 Chỉ build một phần project

Developer vừa build module thư viện, sau đó sửa cấu hình khiến module ấy không còn dependency của application. Nếu output từ build trước vẫn nằm trong classpath, lần compile riêng ứng dụng có thể tiếp tục thành công.

Một máy CI sạch hoặc một máy đồng nghiệp không có artifact cũ sẽ báo lỗi. “Chỉ lỗi trên CI” đôi khi lại là tín hiệu cho thấy **máy local đang dựa vào dữ liệu không được khai báo**.

### 6.4 Class file của version cũ và lỗi chạy khó hiểu

Một `.class` cũ không nhất thiết chỉ che lỗi class bị thiếu; nó còn có thể cung cấp chữ ký API cũ. Sau đó runtime nạp một version thư viện khác, ứng dụng có thể gặp những linkage errors như `NoSuchMethodError` hoặc `NoSuchFieldError` khi code gọi một API không còn tương thích.

Không phải mọi `NoSuchMethodError` đều do stale build. Khi gặp lỗi, hãy kiểm tra class thực tế được nạp, phiên bản thư viện và classpath; tránh chẩn đoán duy nhất theo tên exception.

## 7. Cách tổ chức compile để dễ kiểm tra

### 7.1 Không dùng thư mục output chung làm “kho dependency”

Một anti-pattern là:

~~~bash
javac -cp build/classes -d build/classes src/app/Main.java
~~~

khi `build/classes` chứa cả kết quả của những lần compile trước mà không có cơ chế quản lý obsolete files.

Thay vào đó, ưu tiên:

~~~bash
javac -cp build/lib -d build/app src/app/Main.java
~~~

trong đó `build/lib` là artifact của dependency được build từ đầu vào hợp lệ, còn `build/app` chỉ chứa output của application.

Đây là một **quy ước thiết kế build**; không phải cấm tuyệt đối việc thư mục output xuất hiện trong compile classpath. Một số pipeline cần class đã biên dịch từ vòng trước. Quan trọng là việc tái sử dụng phải được kiểm soát, có dependency graph rõ ràng và có kiểm thử build sạch.

### 7.2 Phân biệt clean output và clean dependency set

“Build sạch” có ít nhất hai tầng ý nghĩa:

1. **Output sạch:** thư mục nhận `.class` ban đầu không chứa artifact cũ.
2. **Input sạch:** compiler không đọc nguồn hoặc binary ngoài dependency được khai báo.

Chỉ tạo `build/clean` rồi vẫn truyền `-cp build/classes` sẽ **không** chứng minh dependency set đã sạch, vì class cũ vẫn được đọc từ `build/classes`. Để xác minh, hãy cấp compiler một classpath gồm đúng các dependency dự kiến.

Đối với ví dụ A3, `-cp build/clean` được chọn để cố ý **không có** `Greeter.class`. Nếu ứng dụng thật cần `Greeter`, hãy khai báo/bắt buộc build dependency này thay vì cố dùng classpath rỗng trong production.

### 7.3 Tên thư mục output cần phản ánh mục đích

Một cấu trúc hữu ích:

~~~text
build/
├── isolated-lib/
├── isolated-app/
├── test-classes/
├── generated-sources/
└── packaged-artifacts/
~~~

Những thư mục này là ví dụ cách đặt tên. Mục đích là tránh trộn source, generated source, class của ứng dụng, class của test và dependency của thư viện vào một nơi mà bạn không còn biết thứ gì đang đóng vai trò **đầu vào** hay **đầu ra**.

### 7.4 Không dùng kết quả compile lần trước để chứng minh tính tái lập

Khi cần review dependency change, CI hoặc release build, một kết quả compile chỉ dựa trên incremental artifacts có giá trị hạn chế. Nên có khả năng chạy một build từ checkout và output mới, với dependency khai báo rõ, không phụ thuộc binary nằm ngoài hệ thống build.

Điều đó không có nghĩa incremental compilation là sai. Incremental compile rất hữu ích cho tốc độ; build system đáng tin cậy phải biết input nào thay đổi và dọn hoặc vô hiệu hóa output nào không còn hợp lệ. Clean build định kỳ là một **phép kiểm chứng độc lập**.

## 8. Kiểm tra artifact và classpath thật

### 8.1 Kiểm tra class file đã sinh

Sau bước A1, dùng công cụ JDK:

~~~bash
javap -classpath build/classes dep.Greeter
javap -classpath build/classes app.Main
~~~

`javap` giải mã thông tin class file; nó không cần chạy `main`. Bạn có thể kiểm tra lớp có tồn tại và chữ ký những thành viên mà compiler nhìn thấy. Để xem thêm bytecode:

~~~bash
javap -c -classpath build/classes app.Main
~~~

Tìm chỉ thị gọi `dep.Greeter.message`. Việc thấy tham chiếu trong bytecode **không bảo đảm** class đích có mặt trên runtime classpath.

### 8.2 Kiểm tra bản class đang được load

Với HotSpot/JDK 17+, bạn có thể quan sát việc nạp class qua unified logging:

~~~bash
java -Xlog:class+load=info -cp build/classes app.Main
~~~

Output sẽ gồm nhiều dòng thông tin JVM; nếu `dep.Greeter` được nạp, log thường cho biết nguồn của class. Dòng log chi tiết phụ thuộc implementation, bản JDK và cấu hình; không nên cố định toàn bộ log làm expected output.

Lệnh chẩn đoán này thuộc HotSpot/unified logging; không phải cam kết rằng mọi JVM vendor đều nhận cú pháp giống hệt.

### 8.3 Kiểm tra classpath lúc chạy

Bạn có thể in thuộc tính hệ thống `java.class.path` trong chương trình Java:

~~~java
System.out.println(System.getProperty("java.class.path"));
~~~

Đây là **một câu lệnh minh họa** có thể đặt trong `main`, không phải chương trình độc lập. Nó giúp thấy các entry classpath theo launcher ở cấu hình thông thường, nhưng không liệt kê mọi nguồn có thể được custom class loader hay module system sử dụng.

### 8.4 Không suy luận nguồn class chỉ từ tên file

Hai file `dep/Greeter.class` ở hai thư mục/JAR khác nhau có thể chứa bytecode khác nhau. Nếu nhiều entry trùng tên trong classpath, class loader thường tìm theo thứ tự và quy tắc của loader; kết quả có thể phụ thuộc cấu hình.

Khi điều tra “tại sao máy này chạy bản cũ”, hãy xem **đường dẫn class được nạp**, classpath, JAR version và log phù hợp. Không chỉ kiểm tra file mà bạn nghĩ là đúng trong thư mục đang mở.

## 9. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Local build thành công, CI sạch báo `cannot find symbol` | Local vẫn có dependency binary cũ trong compile classpath | Build ra thư mục mới, rà soát compile classpath và khai báo dependency |
| Đã xóa file source nhưng ứng dụng vẫn chạy | File `.class` cũ vẫn nằm trong output/JAR/classpath | Xác định artifact được nạp, tạo clean output và kiểm tra packaging |
| `package dep does not exist` khi compile | Compiler không thấy `dep` trong source/classpath được phép | Biên dịch dependency hoặc thêm artifact đúng version vào `-cp` |
| `NoClassDefFoundError: dep/Greeter` lúc chạy | Runtime không tìm được lớp cần thiết dù app có thể đã compile | Thêm dependency vào runtime classpath/đóng gói đúng |
| `NoSuchMethodError` sau khi thay JAR | Compile/runtime có thể dùng API version khác nhau | Kiểm tra version, thứ tự classpath và binary compatibility |
| Chạy ra kết quả cũ sau khi sửa source | Chạy nhầm output hoặc quên biên dịch lại | Kiểm tra `java -cp ...`, artifact và build log |
| `Could not find or load main class app.Main` | Runtime classpath root sai hoặc class chính chưa được tạo | Kiểm tra `build/app/app/Main.class` và tên fully qualified |
| `error: directory not found` khi dùng `-d` | Thư mục output chưa tồn tại hoặc không truy cập được | Tạo đúng output directory và kiểm tra quyền |
| Đổi package rồi vẫn tìm thấy package cũ | Binary cũ chưa được loại bỏ | Build lại vào thư mục output trống và kiểm tra cây class |
| Có `Greeter.class` nhưng compiler vẫn báo lỗi | File nằm ngoài `-cp` hoặc class không tương thích/không đúng tên | Kiểm tra classpath root, package, major version, quyền truy cập và chẩn đoán chi tiết |

### 9.1 Đọc lỗi theo giai đoạn

- `cannot find symbol`, `package ... does not exist`: thường là **compile-time**, compiler không resolve được ký hiệu.
- `NoClassDefFoundError`, `ClassNotFoundException`: liên quan tìm/nạp/khởi tạo class ở **runtime** nhưng hai loại lỗi không hoàn toàn đồng nghĩa; xem stack trace và nguyên nhân.
- `UnsupportedClassVersionError`: runtime không hỗ trợ mức class-file version được nạp.
- `NoSuchMethodError`: thường là lệch binary API giữa artifact lúc compile và lúc chạy, dù có thể có những nguyên nhân khác.

Đừng cố “chữa” mọi lỗi bằng cách thêm bừa nhiều thư mục vào classpath. Cách đó có thể làm build chạy lại trước mắt nhưng tiếp tục che giấu dependency thiếu và tạo xung đột phiên bản.

## 10. Áp dụng khi dùng Gradle, Maven và CI

Các build tool quản lý classpath, dependency graph và output thay bạn; tuy nhiên một vài lỗi vẫn xuất hiện nếu tự viết script hoặc cấu hình task/packaging sai.

### 10.1 Gradle

Với project Java sử dụng Gradle, các task compile có **destination directory** và **classpath** riêng. Build tool có cơ chế theo dõi inputs/outputs và incremental compilation, nhưng không phải mọi artifact tự tạo ngoài convention của Gradle đều được theo dõi đúng nếu cấu hình custom task thiếu thông tin.

Để tự kiểm tra lại từ trạng thái build output sạch khi cần:

~~~bash
./gradlew clean classes
~~~

Trên Windows sử dụng wrapper batch:

~~~powershell
.\gradlew.bat clean classes
~~~

`clean` là task của Gradle xóa output build được quản lý theo cấu hình; nó không xóa các JAR lạ ở một thư mục ngoài build directory nếu script/ứng dụng vẫn chỉ tới đó. Đừng hiểu một lệnh `clean` là đủ để xác minh mọi dependency đầu vào đúng.

Với ứng dụng multi-project, mỗi project cần khai báo dependency thật trong build logic. Ví dụ khái niệm của một module Gradle Java, trong `build.gradle`:

~~~groovy
dependencies {
    implementation project(':library')
}
~~~

Đoạn này chỉ minh họa **khai báo quan hệ giữa hai Gradle project có tên đã được cấu hình phù hợp**, không phải project chạy độc lập. Khi dependency graph khai báo đúng, build tool có cơ sở để compile thư viện trước ứng dụng và đưa đúng output của dependency vào classpath.

### 10.2 Maven

Với project Maven có compiler configuration phù hợp, có thể thực hiện clean build:

~~~bash
mvn clean compile
~~~

Đối với project Java nhiều module, dependency cần khai báo trong POM và reactor/module setup; `clean` của Maven loại bỏ output được quản lý, không tự sửa một JAR sai được tham chiếu ở nơi khác.

Một dependency Maven khai báo minh họa trong `pom.xml`:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>greeter-lib</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Đây là **snippet cấu hình**, các tọa độ chỉ có ý nghĩa nếu artifact tương ứng thật sự tồn tại trong hệ thống dependency. Không thêm một dependency giả vào build để làm ví dụ chạy.

### 10.3 CI là phép thử tái lập hữu ích

CI với checkout sạch và build output mới thường phát hiện vấn đề mà local incremental build bỏ qua. Nhưng CI cũng có cache, nên cần phân biệt **cache dependency hợp lệ** với **output class cũ của lần build khác**.

Một workflow tốt cần:

1. Khai báo chính xác source set và dependency graph.
2. Tránh đọc các thư mục output ngoài cấu hình.
3. Build module theo quan hệ phụ thuộc.
4. Xác minh artifact cuối thay vì chỉ dựa vào exit code của một compiler invocation.
5. Có khả năng chạy clean build trong CI hoặc lúc xác nhận thay đổi dependency.

Build output được cache có thể an toàn nếu khóa cache, theo dõi đầu vào và invalidation đúng. Vấn đề là dùng kết quả **không xác định nguồn gốc** như một dependency hợp lệ.

## 11. Bài tập tự thực hành

### Bài 1 — Dự đoán kết quả ba phép thử

Với cùng source mục 3, hãy đoán kết quả:

~~~bash
javac -d build/classes src/dep/Greeter.java src/app/Main.java
javac -cp build/classes -d build/classes src/app/Main.java
javac -cp build/clean -d build/clean src/app/Main.java
~~~

Giả sử `build/classes` và `build/clean` ban đầu rỗng.

**Đáp án:** lệnh thứ nhất thành công và tạo hai class; lệnh thứ hai thành công nhờ `Greeter.class` được tạo ở lệnh thứ nhất; lệnh thứ ba thất bại vì không thấy package `dep` trên compile classpath sạch.

### Bài 2 — Tách compile-time khỏi runtime

Từ bước B2, chọn lệnh chạy đúng trên Linux/macOS:

~~~bash
java -cp "build/app:build/lib" app.Main
~~~

Nếu bỏ `build/lib`, điều gì xảy ra?

**Đáp án:** `app.Main` có thể được nạp nhưng khi tham chiếu `dep.Greeter` sẽ có lỗi liên quan thiếu class ở runtime, thường là `NoClassDefFoundError` cho `dep/Greeter`. Chương trình không còn in dòng kết quả bình thường.

### Bài 3 — Đổi package của một dependency

Giả sử đổi `dep.Greeter` thành `newdep.Greeter`, đồng thời sửa `app.Main`. Nếu vẫn giữ `build/classes/dep/Greeter.class`, tại sao một source chưa được cập nhật vẫn có thể biên dịch?

**Đáp án:** Source cũ vẫn tham chiếu `dep.Greeter`, và binary cũ có cùng tên vẫn tồn tại trên classpath. Clean output sẽ giúp phát hiện tham chiếu cũ nếu không có dependency tương ứng được khai báo.

### Bài 4 — Kiểm tra tính đầy đủ của dependency graph

Một lần build chỉ compile `Main.java` nhưng muốn được xem là thành công **không phụ thuộc vào artifact cũ** thì cần những gì?

**Đáp án:** Cần đưa `Greeter` vào đầu vào hợp lệ: biên dịch source dependency trong source set thích hợp hoặc build module/JAR thư viện rồi dùng classpath trỏ đúng artifact. Phải dùng output độc lập và không đọc một directory chứa binary còn sót ngoài dependency đã khai báo.

### Bài 5 — Phân biệt `-d` và `-cp`

Vì sao lệnh sau có thể che lỗi?

~~~bash
javac -cp build/classes -d build/classes src/app/Main.java
~~~

**Đáp án:** `-cp build/classes` cho phép compiler đọc binary đã tồn tại ở đó; `-d build/classes` cũng ghi class mới vào cùng nơi. Nếu directory không được dọn và chứa `dep/Greeter.class` cũ, source `Main.java` có thể compile dù dependency hiện tại chưa được cung cấp như mong muốn.

## 12. Checklist trước khi kết luận build sạch

- [ ] Đang compile **đúng tập source** cần kiểm tra, không lấy thêm source ngoài ý định.
- [ ] Mỗi module hoặc phép thử có output directory riêng, có thể tạo mới.
- [ ] Compile classpath chỉ gồm những binary và JAR được khai báo hợp lệ.
- [ ] Không vô tình tham chiếu thư mục output của lần build trước.
- [ ] Đã kiểm tra kết quả trong một **output mới**, không dùng lại `.class` cũ.
- [ ] Khi thay package/xóa source/đổi dependency đã kiểm tra obsolete class files.
- [ ] Runtime classpath chứa đúng dependency cần khi chạy.
- [ ] Đã xem tên lớp đầy đủ, đường dẫn class được nạp và version phù hợp khi gặp lỗi.
- [ ] Build tool/CI quản lý đúng inputs, outputs, cache và dependency graph.
- [ ] Đã quan sát lỗi thật, không thêm tùy tiện classpath entry chỉ để làm compile qua.

## Kết luận

Khi compiler nhìn thấy `.class` cũ trên compile classpath, **nó có quyền dùng file đó để resolve symbol**, kể cả khi source hoặc dependency hiện tại bị thiếu. Vì vậy, thông báo “compile successful” chỉ có nghĩa trong **tập đầu vào thực tế** mà compiler đã đọc. Để biết build có tái lập được hay không, hãy **cô lập output, khai báo rõ dependency và kiểm tra bằng một lần compile từ đầu vào sạch**. Kỹ năng này giúp tìm nguyên nhân các lỗi khó hiểu giữa máy cá nhân, CI và môi trường triển khai Java.