# Biên dịch nhiều tệp trong một lần gọi với javac

## 1. Mục tiêu và tình huống sử dụng

Một ứng dụng Java hiếm khi chỉ có một tệp `.java`. Lớp chạy chính có thể gọi lớp xử lý nghiệp vụ, lớp hỗ trợ nằm ở package khác, hoặc những kiểu dữ liệu cùng tham chiếu lẫn nhau. Khi các tệp thuộc **cùng một đơn vị cần biên dịch**, `javac` cho phép truyền nhiều đường dẫn nguồn trong **một lần gọi**:

```bash
javac -d out src/demo/core/PriceCalculator.java src/demo/core/Receipt.java src/demo/app/Main.java
```

Các tệp được đưa vào cùng lần gọi được trình biên dịch phân tích và biên dịch **như một nhóm**. Khi giải quyết tên và kiểm tra kiểu, `javac` có thể dùng khai báo từ các tệp nguồn cùng nhóm; vì vậy không cần biên dịch từng tệp theo thứ tự sử dụng, và thứ tự tên tệp trên command line không quyết định thứ tự chạy chương trình. Nếu không phát sinh lỗi, các tệp `.class` sẽ được tạo để dùng trên JVM.

Sau bài này, bạn có thể:

- Biên dịch đồng thời nhiều tệp trong cùng package hoặc khác package, rồi chạy đúng lớp chứa `main`.
- Phân biệt nguồn được liệt kê tường minh, nguồn được tìm qua `--source-path` và thư viện `.class`/JAR trên classpath.
- Dùng `@argfile` khi danh sách nguồn dài; hiểu đường dẫn được tính tương đối từ đâu.
- Nhận diện lỗi "cannot find symbol", duplicate class, package sai, thiếu dependency, output cũ và sự khác nhau giữa một lần gọi compiler với hệ thống incremental build.
- Chọn cách tổ chức lệnh ổn định cho dự án nhỏ, script và CI.

**Phạm vi:** ví dụ chính dùng dự án Java không khai báo module (`module-info.java`), chạy được với JDK 17 trở lên. Dự án JPMS nhiều module có thêm quy tắc `--module-source-path` và `--module-path`, được phân biệt ở phần sau.

## 2. Cú pháp cơ bản: nhiều source file, một tiến trình javac

```text
javac [options] SourceA.java SourceB.java SourceC.java ...
```

Mỗi tham số nguồn là đường dẫn đến một file `.java`. Ví dụ:

```bash
javac Alpha.java Beta.java Gamma.java
```

Nếu không dùng `-d`, compiler mặc định đặt file `.class` trong thư mục chứa file nguồn tương ứng. Với dự án có package, hãy đặt kết quả vào một thư mục riêng:

```bash
javac -d out Alpha.java Beta.java Gamma.java
```

`-d out` yêu cầu `javac` tổ chức file đầu ra theo package bên dưới `out`; `javac` tạo thư mục đích và các thư mục package cần thiết nếu chưa tồn tại. Điều này giúp tách nguồn khỏi artifact. Khi chạy chương trình thuộc unnamed module, đặt **thư mục gốc output** trên classpath bằng `java -cp out <tên.lớp.đầy.đủ>`.

Một lệnh có ba file nguồn **không tương đương** ba lần gọi compiler riêng biệt:

```bash
# Một lần gọi: compiler nhìn thấy ba nguồn được chỉ định cùng lúc
javac -d out Alpha.java Beta.java Gamma.java
```

```bash
# Ba lần gọi: mỗi lệnh có môi trường nhìn thấy các nguồn/classfile riêng
javac -d out Alpha.java
javac -d out Beta.java
javac -d out Gamma.java
```

Với các lệnh riêng, mỗi lần phải tìm được những kiểu mà nguồn đang tham chiếu thông qua chính nguồn được chỉ định, classpath hoặc source path. Kết quả có thể phụ thuộc file `.class` đã tạo ở bước trước, và **`-d out` không tự động thêm `out` vào compile classpath của dự án không dùng module**. Ngược lại, một lần gọi cùng nhóm cho phép các khai báo nguồn hỗ trợ lẫn nhau mà không cần sắp thứ tự file thủ công.

## 3. Ví dụ đầy đủ: ba file, hai package, một lệnh

Giả sử có cấu trúc thư mục:

```text
compile-together/
└── src/
    └── demo/
        ├── app/
        │   └── Main.java
        └── core/
            ├── PriceCalculator.java
            └── Receipt.java
```

### File 1 — `src/demo/core/PriceCalculator.java`

```java
package demo.core;

public final class PriceCalculator {
    private PriceCalculator() {
    }

    public static int total(int quantity, int unitPrice) {
        return quantity * unitPrice;
    }
}
```

Lớp này cung cấp phép tính. Vì có `public`, tên file phải phù hợp với tên lớp `PriceCalculator`.

### File 2 — `src/demo/core/Receipt.java`

```java
package demo.core;

public final class Receipt {
    private Receipt() {
    }

    public static String format(int quantity, int unitPrice) {
        int total = PriceCalculator.total(quantity, unitPrice);
        return quantity + " x " + unitPrice + " = " + total;
    }
}
```

`Receipt` dùng `PriceCalculator` trong cùng package `demo.core`, không cần `import` nội bộ package.

### File 3 — `src/demo/app/Main.java`

```java
package demo.app;

import demo.core.Receipt;

public class Main {
    public static void main(String[] args) {
        System.out.println(Receipt.format(3, 12));
    }
}
```

`Main` ở package `demo.app` nên import lớp `Receipt` công khai từ package `demo.core`.

### Biên dịch và chạy

Mở terminal tại thư mục `compile-together`, nơi chứa `src`. Chạy:

```bash
javac -encoding UTF-8 -d out src/demo/core/PriceCalculator.java src/demo/core/Receipt.java src/demo/app/Main.java
java -cp out demo.app.Main
```

Đầu ra của lệnh `java`:

```text
3 x 12 = 36
```

`javac` thành công thường không in thông báo. Output dự kiến sau lần biên dịch gồm:

```text
out/
└── demo/
    ├── app/
    │   └── Main.class
    └── core/
        ├── PriceCalculator.class
        └── Receipt.class
```

Những điểm cần hiểu:

1. `src` là **gốc cây nguồn**; `out` là **gốc cây class file**.
2. Tên package được khai báo trong mã là `demo.app` và `demo.core`; dấu chấm trong tên package tương ứng với thư mục con ở output.
3. Cả ba file được đưa vào cùng lần gọi, nên compiler có thể liên kết tham chiếu `Main → Receipt → PriceCalculator` bằng khai báo từ các file đó.
4. Khi chạy, dùng tên lớp đầy đủ `demo.app.Main`. Gọi `java -cp out Main` sẽ không tìm đúng lớp vì tên binary của nó có package.
5. Thêm một source file vào command line chỉ yêu cầu biên dịch file đó; **không** có nghĩa lớp của file đó tự động trở thành entry point. Phương thức `main` cần chọn khi dùng lệnh `java`.
6. `-encoding UTF-8` làm rõ cách đọc văn bản nguồn. Nếu hướng tới runtime Java 17 từ JDK mới hơn, có thể thêm `--release 17` theo chính sách tương thích của dự án.

## 4. Thứ tự file nguồn và giải quyết phụ thuộc

Hãy thử thay thứ tự các tham số:

```bash
javac -encoding UTF-8 -d out src/demo/app/Main.java src/demo/core/Receipt.java src/demo/core/PriceCalculator.java
```

Cả hai cách liệt kê đều hợp lệ; `javac` biên dịch nhóm nguồn cùng nhau. **Không cần viết file phụ thuộc trước file sử dụng nó.** Đây là khác biệt lớn so với việc tự thiết kế script chạy nhiều lệnh `javac` độc lập.

### Trường hợp hai lớp cùng tham chiếu lẫn nhau

Hai file sau có thể được biên dịch cùng lượt dù mỗi kiểu dùng tên kiểu của file còn lại.

`NodeA.java`:

```java
public class NodeA {
    NodeB other;
}
```

`NodeB.java`:

```java
public class NodeB {
    NodeA other;
}
```

```bash
javac -d out NodeA.java NodeB.java
```

Hai trường tham chiếu lẫn nhau là hợp lệ. Đây **không phải** ví dụ về một vòng kế thừa lớp (ví dụ `A extends B` đồng thời `B extends A`), vốn là lỗi compile-time. Một lần gọi nhóm nguồn giải quyết được khai báo phụ thuộc qua lại, nhưng không làm những mối quan hệ bị Java cấm trở nên hợp lệ.

Tùy vị trí thư mục và cấu hình tìm nguồn, biên dịch riêng `NodeA.java` đôi khi cũng thành công vì `javac` tự tìm `NodeB.java`. Vì thế không nên khẳng định rằng "biên dịch một file luôn lỗi"; cần kiểm tra chính xác **source path/classpath** lúc gọi.

## 5. Ba cách để javac nhìn thấy các kiểu phụ thuộc

Khi gặp `import demo.core.Receipt;` hoặc một tham chiếu kiểu, compiler phải tìm được khai báo của nó. Có ba đường phổ biến:

| Cách cung cấp | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Liệt kê trực tiếp file nguồn** | `javac -d out A.java B.java` | Cả `A.java` và `B.java` là nguồn đầu vào của cùng lần gọi |
| **Đặt nguồn bổ sung trên source path** | `javac --source-path src -d out src/demo/app/Main.java` | Cho phép compiler tìm nguồn phụ thuộc dưới cây `src` theo package |
| **Đặt binary/JAR trên classpath** | `javac -cp out -d other-out Consumer.java` | Sử dụng các kiểu đã biên dịch, không đòi hỏi mọi nguồn gốc phải được biên dịch lại |

### 5.1. Liệt kê tường minh — dễ kiểm soát phạm vi

Đối với ví dụ ba file, cách an toàn và dễ đọc nhất là lệnh ở mục 3. Đặc biệt khi có annotation processors hoặc cần biết chính xác tập nguồn được build, một danh sách tường minh giúp hạn chế sự khác biệt do tìm file ngầm.

### 5.2. `--source-path` — tìm thêm file nguồn

Có thể bắt đầu với `Main.java` và cho compiler biết cây nguồn chứa những kiểu khác:

```bash
javac -encoding UTF-8 -d out --source-path src src/demo/app/Main.java
```

Vì `Receipt.java` và `PriceCalculator.java` nằm đúng vị trí package dưới `src`, `javac` có thể tìm và biên dịch chúng như nguồn phụ thuộc khi cần. Theo mặc định, `javac` có thể sinh class file cho các nguồn được phát hiện ngầm; `-implicit:none` có thể tắt việc tạo các class file đó. Nếu bài build yêu cầu tất cả nguồn được xử lý annotation một cách dự đoán được, hãy cân nhắc liệt kê trực tiếp mọi file cần biên dịch.

Nếu **không** chỉ định source path khi biên dịch dự án không dùng module, user classpath cũng được tìm để lấy source file. Điều này đôi khi khiến lệnh chỉ truyền một file vẫn "tự biết" file còn lại. Để script ổn định và dễ tái hiện, hãy chủ động cấu hình source path hoặc liệt kê đầy đủ, tránh phụ thuộc hành vi tình cờ của working directory.

### 5.3. `-cp` / `--class-path` — dùng dependency đã biên dịch

Nếu `Receipt` đã có file `.class` dưới `out` và bạn muốn biên dịch riêng một client dùng nó:

```bash
javac -cp out -d client-out src/demo/app/Main.java
```

Lệnh này sử dụng `out` như một **classpath tại thời điểm biên dịch**. Khi chạy `Main`, vẫn cần cho JVM thấy cả client lẫn dependency. Dấu phân cách classpath phụ thuộc hệ điều hành:

```bash
# Linux/macOS:
java -cp "client-out:out" demo.app.Main
```

```powershell
# Windows PowerShell:
java -cp "client-out;out" demo.app.Main
```

Hai lệnh trên được dùng **sau khi** đã biên dịch `PriceCalculator` và `Receipt` vào `out`. Lưu ý: đây là tình huống sử dụng dependency đã biên dịch; không cần biên dịch lại cả nhóm nếu dependency không thay đổi, nhưng phải bảo đảm binary đủ mới và tương thích.

Đối với JAR bên ngoài, truyền đường dẫn thư viện bằng `-cp` khi compile và dùng classpath phù hợp khi run. `-cp` không có chức năng tự cài đặt hoặc tải thư viện.

## 6. Danh sách nhiều file dài: argument file `@sources.txt`

Hệ điều hành có giới hạn chiều dài command line. Khi số file nhiều, thay vì một lệnh dài khó bảo trì, tạo file chứa tên nguồn:

`sources.txt`:

```text
src/demo/core/PriceCalculator.java
src/demo/core/Receipt.java
src/demo/app/Main.java
```

Sau đó từ thư mục `compile-together`:

```bash
javac -encoding UTF-8 -d out @sources.txt
java -cp out demo.app.Main
```

Output của `java` vẫn là:

```text
3 x 12 = 36
```

`@sources.txt` bảo `javac` đọc các đối số trong file thay cho việc nhập tất cả trên dòng lệnh. Đây vẫn là **một lần gọi compiler**, các source files vẫn được biên dịch như một nhóm.

Các quy tắc quan trọng:

- Mỗi tên file có thể nằm trên một dòng; file arg cũng có thể chứa các tùy chọn khác của `javac`.
- Đường dẫn nguồn **bên trong argfile** được hiểu tương đối từ **working directory lúc gọi `javac`**, không phải thư mục chứa argfile. Nếu chạy ở thư mục khác, hãy điều chỉnh đường dẫn.
- Nếu tên file hoặc đường dẫn có khoảng trắng, đặt **toàn bộ tên đó** trong dấu nháy kép bên trong argfile: `"src/demo/my sources/Extra.java"`.
- Không viết `src/**/*.java` hoặc `*.java` vào argfile với kỳ vọng `javac` tự expand wildcard: cú pháp wildcard như vậy không được hỗ trợ trong danh sách argument file.
- Không dùng `@file-khac` bên trong argfile để lồng argfile: việc giải mã đệ quy như vậy không được hỗ trợ.
- Nếu danh sách nguồn tạo tự động, phải tạo danh sách các đường dẫn thật sự và trích dẫn đúng các đường dẫn có khoảng trắng.

Có thể đưa cả option vào `compile.args`:

```text
-encoding
UTF-8
-d
out
src/demo/core/PriceCalculator.java
src/demo/core/Receipt.java
src/demo/app/Main.java
```

```bash
javac @compile.args
```

Với ví dụ này, output vẫn nằm dưới `out`. Khi kết hợp `@argfile` với tham số trực tiếp, cần hiểu cuối cùng `javac` nhận một danh sách tùy chọn và file nguồn sau khi mở rộng, chứ không phải hai lượt compile.

## 7. Chọn danh sách file theo môi trường

### 7.1. Liệt kê cụ thể

Cho dự án nhỏ hoặc tài liệu học, nêu cụ thể ba file như ví dụ là cách ít phụ thuộc môi trường nhất.

### 7.2. Wildcard của shell không đồng nghĩa wildcard của javac

Lệnh như:

```bash
javac -d out src/demo/core/*.java src/demo/app/Main.java
```

có thể chạy trong shell POSIX vì **shell** mở rộng `*.java` thành các file thực tế trước khi `javac` nhận đối số. Nhưng khi chạy trong PowerShell, CMD, IDE hoặc một chương trình gọi `javac` trực tiếp, không được giả định cùng cơ chế mở rộng glob. Wildcard này cũng chỉ chọn file trực tiếp trong thư mục `core`, không có ý nghĩa tự động quét đệ quy toàn bộ cây `src`.

Muốn quét dự án lớn trên nhiều nền tảng, dùng công cụ build như Gradle/Maven hoặc viết script tạo danh sách nguồn thật rồi truyền cho `javac`. Đặc biệt tránh đưa dấu `*` vào `@sources.txt` rồi hy vọng được mở rộng.

### 7.3. Không compile mọi `.java` một cách mù quáng

Một repository có thể chứa nhiều source set và module: `src/main/java`, `src/test/java`, mẫu code, mã sinh tự động hoặc nhiều ứng dụng độc lập. Gộp tất cả vào một lệnh có thể gây duplicate class, phụ thuộc test chưa cấu hình, processor chạy sai phạm vi hoặc mâu thuẫn module. "Biên dịch nhiều tệp trong một lần gọi" nghĩa là đưa **nhóm nguồn phù hợp** vào compiler, không có nghĩa biên dịch mọi file tìm thấy dưới repository.

## 8. Một lệnh compile tạo ra gì và không làm gì?

Giả sử `javac` biên dịch thành công ba file trên. Trong `out` có thể xuất hiện nhiều class file hơn số source file nếu nguồn còn chứa nested class, anonymous class hoặc những kiểu bổ sung. Vì vậy số lượng `.class` không luôn bằng số lượng `.java`.

Cần phân biệt:

- **Compile:** kiểm tra cú pháp/kiểu và tạo class file (`javac`).
- **Run:** chọn một class có entry point thích hợp và thực thi (`java`).
- **Package:** tạo JAR hoặc artifact phân phối (`jar` hay build tool).
- **Test:** chạy bộ kiểm thử, không tự động được kích hoạt chỉ vì biên dịch thành công.

`javac` không chạy các phương thức `main` của các file nguồn. Trường hợp có nhiều lớp chứa `main`, một lần biên dịch vẫn có thể tạo class files cho tất cả; lúc chạy bạn chọn đúng main class. Compile thành công cũng không bảo đảm chương trình sẽ tìm được mọi dependency tại runtime hoặc không phát sinh ngoại lệ.

Với các source files có package, vị trí file đầu ra do tên package và tùy chọn `-d` quyết định; đặt `out/demo/app/Main.class` vào classpath **không** có nghĩa dùng `java -cp out/demo/app Main` khi class được khai báo `package demo.app`. Gốc classpath phải là `out`.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Kiểm tra / xử lý |
| --- | --- | --- |
| `cannot find symbol` cho kiểu ở file khác | File phụ thuộc không nằm trong nhóm, source path hoặc classpath; khai báo sai tên/package | Kiểm tra đường dẫn `.java`, `package`, `import`, `--source-path` và `-cp` |
| `package ... does not exist` | Compiler không tìm được các kiểu cần thiết thuộc package đó | Liệt kê đúng file nguồn hoặc thêm đường dẫn source/classpath phù hợp |
| `duplicate class` | Có nhiều định nghĩa cùng tên nhị phân trong nhóm hoặc chọn nhầm nguồn trùng | Loại file trùng, tách đúng source set; không gộp mọi directory tùy tiện |
| Lỗi tên file của `public class` | Tên nguồn không khớp public top-level class | Đổi tên `.java` theo đúng kiểu công khai |
| `Could not find or load main class` sau compile | Dùng sai full qualified name hoặc sai classpath root | Chạy `java -cp out demo.app.Main` và xác nhận `out/demo/app/Main.class` |
| `NoClassDefFoundError` / `ClassNotFoundException` khi chạy | Runtime classpath thiếu dependency hoặc artifact | Cung cấp đúng thư viện và output đã biên dịch trong lệnh `java` |
| `NoSuchMethodError` / `NoSuchFieldError` | Binary dependency không tương thích với phiên bản mà client được compile | Dọn và biên dịch lại những module liên quan; kiểm tra runtime classpath |
| File `.class` cũ vẫn còn sau build lỗi | `javac -d` không có nghĩa xóa thư mục output cũ hoặc commit nguyên tử | Build vào output sạch; kiểm tra exit code và xử lý artifact thất bại |
| `@sources.txt` không tìm file | Các đường dẫn trong argfile được hiểu theo working directory hiện tại | Kiểm tra `pwd`/working directory và tên file chính xác |
| Tên đường dẫn có khoảng trắng bị tách | Chưa quote đúng tham số hoặc nội dung argfile | Đặt đường dẫn trong dấu nháy kép theo cú pháp tương ứng |

**Lưu ý về lỗi và artifact:** một lần gọi `javac` không phải giao dịch atomic theo nghĩa hệ thống tệp. Nếu một hoặc nhiều nguồn lỗi, không nên dựa vào việc thư mục output chắc chắn không có file class mới hoặc file class cũ. Hãy kiểm tra mã thoát của `javac` và dùng output sạch khi cần kiểm chứng chính xác kết quả build.

**Lưu ý về cảnh báo:** có thể bật `-Xlint` và `-Werror` theo chính sách dự án. Các tùy chọn này không thay đổi bản chất "một lần gọi nhiều nguồn" nhưng có thể khiến lệnh thất bại khi gặp cảnh báo.

## 10. Biên dịch lặp lại, incremental build và tính tái lập

Lệnh:

```bash
javac -d out src/demo/core/PriceCalculator.java src/demo/core/Receipt.java src/demo/app/Main.java
```

yêu cầu compiler xử lý tập nguồn được truyền ở lần gọi đó; **không tự trở thành hệ thống quản lý dependency và incremental build hoàn chỉnh**. `javac` có khả năng tìm/biên dịch thêm nguồn theo cấu hình, nhưng nó không tự duy trì toàn bộ đồ thị task của repository, quản lý test resources, dependency versions, cache build hay xóa các binary không còn tương ứng với mã nguồn.

Khi sửa chữ ký của `PriceCalculator.total`, những file dùng phương thức ấy có thể cần được compile lại. Nếu chạy nhiều lần lệnh riêng với `.class` cũ, bạn có thể vô tình biên dịch hoặc chạy với định nghĩa không nhất quán. Biên dịch cùng một nhóm từ output sạch giúp loại bớt vấn đề này trong ví dụ nhỏ. Dự án thực tế nên để Gradle/Maven xác định source set, classpath, thứ tự task và phạm vi cần rebuild.

Để kết quả dễ tái hiện, ghi rõ:

1. Phiên bản JDK/compiler: `javac -version`.
2. Mức API/ngôn ngữ/runtime mong muốn: ví dụ `--release 17` khi build trên JDK hỗ trợ.
3. Danh sách nguồn hoặc cách sinh danh sách nguồn.
4. Compile classpath/module path và các annotation processors.
5. Thư mục output sạch và mã thoát compiler; không dùng artifact từ lệnh thất bại để xác nhận kết quả.

Với dự án nhỏ của bài này, có thể dùng lệnh sau để yêu cầu Java 17 khi dùng JDK 17+ có hỗ trợ mục tiêu đó:

```bash
javac --release 17 -encoding UTF-8 -d out @sources.txt
java -cp out demo.app.Main
```

Kết quả vẫn là `3 x 12 = 36`. `--release 17` giới hạn cả ngôn ngữ, định dạng class file và API Java SE tương ứng; tuy vậy vẫn phải đảm bảo runtime/dependency thích hợp khi chạy ở môi trường thực tế.

## 11. Khi dự án dùng Java Platform Module System (JPMS)

Các ví dụ trước biên dịch lớp trên classpath, không có `module-info.java`. Nếu dự án có module rõ ràng, hãy phân biệt:

- Nguồn trong **một module** có thể được liệt kê đồng thời, cùng với `module-info.java`, và đặt output vào cấu trúc module tương ứng.
- Khi biên dịch **nhiều module** trong một lượt, `javac` có chế độ dành riêng dùng `--module-source-path` để nhận diện và tìm nguồn các module; binary dependency có thể được tìm qua `--module-path`.
- Lệnh chạy chương trình module thường dùng `java --module-path ... --module moduleName/package.Main`, thay vì xem tất cả class file như một cây classpath không tên.

Không hoán đổi `--source-path` và `--module-source-path` một cách máy móc. Phần này chỉ xác định phạm vi: chủ đề "nhiều tệp trong một lần gọi" vẫn đúng, nhưng cấu trúc thư mục, dependency và cách chạy của JPMS phải tuân theo chế độ module.

## 12. Quy trình thực hành cho một nhóm nguồn

1. **Xác định nhóm nguồn** cần biên dịch cùng nhau; kiểm tra các package và các loại phụ thuộc.
2. **Đặt một thư mục output riêng**, ví dụ `out`; sử dụng `-d out` để sinh class file theo cấu trúc package.
3. **Chọn đầu vào:** liệt kê file tường minh khi ít, hoặc tạo `@sources.txt` chính xác khi nhiều. Nếu dùng `--source-path`, hiểu rõ việc tìm và compile nguồn ngầm.
4. **Cung cấp binary dependencies** trên compile classpath/module path, và chọn `--release` phù hợp.
5. **Chạy một lần `javac`**, kiểm tra exit code và log lỗi. Không giả định file ghi trước trên command line được compile trước.
6. **Chạy đúng main class** từ thư mục output bằng lệnh `java` với classpath/module path phù hợp.
7. Khi cần kiểm chứng build, **tránh class file tồn dư**, ghi nhận JDK và tùy chọn đã dùng.

## 13. Tự kiểm tra

**Câu 1.** Trong ví dụ ba file, đổi thứ tự command line thành `Main.java Receipt.java PriceCalculator.java` thì có phải thêm `import` mới?

**Đáp án:** Không. `import` phụ thuộc tên package/type, không phụ thuộc thứ tự tham số nguồn. `javac` giải quyết khai báo từ các file được truyền cùng nhóm.

**Câu 2.** File `sources.txt` đặt trong thư mục `config`, nội dung là `src/demo/app/Main.java`. Chạy `javac @config/sources.txt` từ một thư mục cha khác có bảo đảm tìm đúng file không?

**Đáp án:** Không. Đường dẫn trong argfile tính từ working directory lúc gọi `javac`; vị trí file arg không làm thay đổi cơ sở đường dẫn của các entry.

**Câu 3.** Lệnh `javac -d out src/demo/app/Main.java` có chắc chắn thất bại vì chỉ truyền một file?

**Đáp án:** Không thể kết luận chỉ từ lệnh. Compiler có thể tìm class file hay source phụ thuộc theo classpath/source path cấu hình. Liệt kê đủ nguồn hoặc đặt `--source-path` rõ ràng giúp kết quả dễ dự đoán.

**Câu 4.** Sau khi compile thành công, tại sao `java -cp out Main` không chạy `demo.app.Main`?

**Đáp án:** `Main` đã khai báo `package demo.app`. Tên binary đầy đủ là `demo.app.Main`, và classpath root là `out`.

**Câu 5.** Một file trong nhóm bị lỗi kiểu. Có được coi mọi file `.class` dưới `out` là artifact hợp lệ của lần build vừa thực hiện không?

**Đáp án:** Không. Kiểm tra mã thoát, không dùng artifact sau build thất bại; dùng output sạch để tránh class file tồn từ build trước.

## 14. Tài liệu tham khảo

- **Oracle JDK 21 — The javac Command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html — mục *Synopsis*, *Example of Compiling Multiple Source Files*, *Command-Line Argument Files*, *Configuring a Compilation* và *Searching for Module, Package and Type Declarations*.
- **Java Language Specification, Java SE 21:** https://docs.oracle.com/javase/specs/jls/se21/html/ — các quy tắc về package, tên kiểu, khả năng truy cập và lỗi compile-time.
- **Java Virtual Machine Specification, Java SE 21:** https://docs.oracle.com/javase/specs/jvms/se21/html/ — cấu trúc class file và liên kết kiểu ở runtime.

Điều cần nhớ khi thực hành: **một lần gọi `javac` có thể nhận nhiều tệp nguồn và biên dịch chúng như một nhóm; tổ chức package, source path, classpath và output directory quyết định compiler tìm thấy gì và chương trình chạy được hay không**.