# Biên dịch chương trình có package từ đúng thư mục gốc

## 1. Mục tiêu và ý chính

Với một chương trình Java có package, cần biết **terminal đang đứng ở đâu**, **các tệp nguồn nằm dưới thư mục gốc nào**, **tên package là gì**, và **gốc chứa các tệp .class sau khi biên dịch**. Bốn khái niệm này liên quan chặt chẽ nhưng khác nhau.

Sau bài học, bạn có thể:

- Tạo một dự án Java 17+ có hai package và biên dịch bằng javac không cần IDE hoặc build tool.
- Chạy đúng lệnh từ **gốc dự án** hoặc **gốc mã nguồn**, bằng cách điều chỉnh đường dẫn tương đối.
- Hiểu chính xác -d, -cp, -sourcepath và tên lớp đầy đủ.
- Tự kiểm tra vị trí .class, chạy chương trình với java, dùng javap và chẩn đoán lỗi “file not found”, “cannot find symbol”, “Could not find or load main class”.

**Quy tắc cốt lõi:** từ thư mục làm việc hiện tại, truyền đúng đường dẫn tới .java cho javac; ghi .class dưới một thư mục đầu ra đã xác định; chạy bằng classpath **trỏ tới gốc cây bytecode** và **tên lớp đầy đủ gồm package**.

## 2. Phân biệt bốn loại “gốc”

Xét cấu trúc dự án:

~~~text
package-lab/                     <-- Gốc dự án
├── src/                         <-- Gốc mã nguồn
│   └── com/
│       └── example/
│           ├── app/
│           │   └── Main.java
│           └── text/
│               └── Greeter.java
└── out/                         <-- Gốc đầu ra bytecode
    └── com/
        └── example/
            ├── app/
            │   └── Main.class
            └── text/
                └── Greeter.class
~~~

1. **Current working directory (CWD)**: thư mục hiện tại của terminal. Đường dẫn tương đối trong các lệnh được tính từ CWD. Ví dụ chính dùng CWD = package-lab.
2. **Source root**: thư mục phía trên cây package của nguồn. Ở đây là src. Tên package com.example.app tương ứng đường dẫn tương đối com/example/app bên dưới src.
3. **Package**: tên định danh trong mã Java, ví dụ package com.example.app;. Đây là không gian tên, không phải chỉ dẫn terminal đổi thư mục.
4. **Output root / classpath root**: thư mục phía **trên** cây package chứa .class. Ở đây là out. Nếu Main.class ở out/com/example/app/Main.class thì classpath phải chứa out, không phải out/com/example/app.

Với lệnh -d out, javac đặt bytecode vào đúng cây package bên dưới out. Khi chạy theo classpath, JVM ánh xạ tên com.example.app.Main thành đường dẫn com/example/app/Main.class tương đối với từng classpath root.

**Quy tắc nguồn cần nhớ:** tệp chứa public top-level class Main phải tên Main.java. Đặt file trong nhánh thư mục phù hợp với khai báo package là quy ước chuẩn và làm các công cụ tìm nguồn hoạt động rõ ràng. Tuy nhiên, không có quy định rằng terminal bắt buộc luôn đứng ngay trong src hoặc ngay trong thư mục package.

## 3. Chuẩn bị một dự án chạy được

Dùng **JDK 17 trở lên**. Kiểm tra cả công cụ biên dịch và trình chạy:

~~~sh
javac -version
java -version
~~~

Tạo thư mục package-lab với hai nhánh src/com/example/text và src/com/example/app. Đặt chính xác hai tệp sau vào hai nhánh tương ứng. Nếu dùng IDE để tạo tệp, vẫn thực hiện lệnh biên dịch trong terminal để thấy rõ đường dẫn và đầu ra.

### src/com/example/text/Greeter.java

~~~java
package com.example.text;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Lớp Greeter thuộc package com.example.text; tên đầy đủ của nó là com.example.text.Greeter. Phương thức public static greet nhận tên và trả lời chào. Constructor private vì ví dụ không cần khởi tạo đối tượng Greeter.

### src/com/example/app/Main.java

~~~java
package com.example.app;

import com.example.text.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.greet("Lan"));
    }
}
~~~

Lớp Main thuộc package **khác** với Greeter. Khai báo import cho phép dùng tên ngắn Greeter thay vì viết tên đầy đủ tại mọi lời gọi. javac phải nhìn thấy lớp Greeter khi biên dịch Main.

Đây là **hai tệp .java tách biệt**, mỗi tệp có khai báo package và public class riêng. Không ghép hai lớp public vào cùng một tệp.

## 4. Biên dịch từ gốc dự án: cách dễ kiểm chứng nhất

Giả sử terminal đang ở thư mục cha của package-lab, hãy chuyển vào gốc dự án:

~~~sh
cd package-lab
~~~

Kiểm tra thư mục hiện tại bằng pwd (Bash/macOS/Linux) hoặc Get-Location (PowerShell). Từ đây, đường dẫn src/com/example/app/Main.java phải tồn tại.

Tạo out trước khi biên dịch. Chọn lệnh phù hợp hệ điều hành:

~~~bash
# Bash
mkdir -p out
~~~

~~~powershell
# PowerShell
New-Item -ItemType Directory -Path out -Force | Out-Null
~~~

Chạy lệnh biên dịch **cả hai tệp nguồn** từ CWD = package-lab:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/com/example/text/Greeter.java src/com/example/app/Main.java
~~~

Khi thành công, javac thường không in thông báo. Kiểm tra out, bạn sẽ thấy:

~~~text
out/
└── com/
    └── example/
        ├── app/
        │   └── Main.class
        └── text/
            └── Greeter.class
~~~

Chạy ứng dụng từ **cùng thư mục package-lab**:

~~~sh
java -cp out com.example.app.Main
~~~

**Stdout chính xác:**

~~~text
Hello, Lan!
~~~

Giải thích từng bước:

1. CWD là package-lab, nên hai đường dẫn bắt đầu bằng src/... được hiểu tương đối từ gốc dự án.
2. javac đọc cả hai file; khai báo package cung cấp tên đầy đủ của mỗi lớp.
3. -d out yêu cầu sinh class bên dưới out, tổ chức các thư mục con theo package.
4. JVM nhận -cp out và tìm com/example/app/Main.class, cũng như com/example/text/Greeter.class, từ gốc out.
5. com.example.app.Main chỉ đúng lớp chứa main, gồm package và tên lớp.

| Thành phần | Ý nghĩa |
| --- | --- |
| javac | Chương trình biên dịch Java |
| -encoding UTF-8 | Giải mã tệp nguồn bằng UTF-8 |
| --release 17 | Biên dịch theo cú pháp, API platform và bytecode đích Java 17 |
| -d out | Nơi javac ghi các .class và tạo cây package |
| src/com/example/.../Tên.java | Đường dẫn tới **tệp nguồn**, tính từ CWD |
| java | Trình khởi động ứng dụng Java/JVM |
| -cp out | Gốc tìm kiếm lớp đã biên dịch khi chạy |
| com.example.app.Main | Tên lớp đầy đủ chứa phương thức main |

**Lưu ý:** -d yêu cầu thư mục gốc đầu ra đã có; ví dụ đã tạo out. javac tạo các thư mục package con khi cần. Hai tệp nguồn được liệt kê tường minh nên lệnh biên dịch không phụ thuộc vào cú pháp mở rộng wildcard khác nhau giữa Bash và PowerShell.

## 5. Vì sao không đặt classpath là out/com/example/app?

Tên đầy đủ của lớp Main là com.example.app.Main. Với classpath, JVM quy đổi tên đó thành:

~~~text
Tên lớp:      com.example.app.Main
Nhánh cần có: com/example/app/Main.class
Classpath:    out
Kết quả:      out/com/example/app/Main.class
~~~

Nếu dùng -cp out/com/example/app, JVM lại tiếp tục tìm com/example/app/Main.class **bên dưới** thư mục đó. Đây là nguyên nhân phổ biến của lỗi không tìm thấy lớp main.

Các lệnh sau **không đúng với cây bytecode của ví dụ sạch này**:

~~~sh
java -cp out/com/example/app com.example.app.Main
java -cp out Main
java -cp src com.example.app.Main
~~~

Lệnh thứ nhất chọn sai gốc; lệnh thứ hai bỏ package nên tìm lớp Main trong default package; lệnh thứ ba trỏ vào cây mã nguồn .java, trong khi .class đã được sinh tại out.

Sửa bằng lệnh đã xác minh:

~~~sh
java -cp out com.example.app.Main
~~~

Nếu ở một dự án khác, lệnh có vẻ sai nhưng lại chạy, có thể JVM đang thấy artifact cũ hoặc cùng tên trong vị trí khác. Hãy kiểm tra .class thật sự được nạp, thay vì kết luận cách đặt classpath sai vẫn được bảo đảm.

## 6. Biên dịch từ gốc mã nguồn src cũng hợp lệ

“Đúng thư mục gốc” có nghĩa **mọi đường dẫn được tính nhất quán từ CWD**, chứ không có một thư mục duy nhất mà javac bắt buộc phải chạy từ đó.

Ở CWD = package-lab, chuyển vào src:

~~~sh
cd src
~~~

Bây giờ CWD là **package-lab/src**. Nếu out chưa tồn tại, có thể tạo ở thư mục cha:

~~~bash
# Bash
mkdir -p ../out
~~~

~~~powershell
# PowerShell
New-Item -ItemType Directory -Path ../out -Force | Out-Null
~~~

Biên dịch từ src:

~~~sh
javac -encoding UTF-8 --release 17 -d ../out com/example/text/Greeter.java com/example/app/Main.java
~~~

Chạy từ **CWD = package-lab/src**:

~~~sh
java -cp ../out com.example.app.Main
~~~

Stdout vẫn là:

~~~text
Hello, Lan!
~~~

Từ src, đường dẫn đến tệp nguồn không còn tiền tố src/, và out nằm ở thư mục cha nên dùng ../out. Nếu vẫn gõ src/com/example/app/Main.java từ CWD = src, compiler sẽ tìm src/src/com/example/app/Main.java và có thể báo “file not found”.

Quay về gốc dự án nếu cần:

~~~sh
cd ..
~~~

| CWD | Nguồn Main.java | -d | -cp khi chạy | Lớp main |
| --- | --- | --- | --- | --- |
| package-lab | src/com/example/app/Main.java | out | out | com.example.app.Main |
| package-lab/src | com/example/app/Main.java | ../out | ../out | com.example.app.Main |

Tên package và tên lớp đầy đủ **không đổi** khi đổi CWD. Chỉ có đường dẫn tương đối dùng trong terminal thay đổi.

## 7. -cp và -sourcepath khác -d như thế nào?

### Biên dịch từng lớp: compiler cần thấy .class đã có

Từ CWD = package-lab, tạo out nếu cần rồi biên dịch Greeter trước:

~~~sh
javac -encoding UTF-8 --release 17 -d out src/com/example/text/Greeter.java
~~~

Bây giờ Greeter.class nằm dưới out. Biên dịch riêng Main:

~~~sh
javac -encoding UTF-8 --release 17 -cp out -d out src/com/example/app/Main.java
~~~

Chạy:

~~~sh
java -cp out com.example.app.Main
~~~

Kết quả vẫn là Hello, Lan!.

Trong lệnh thứ hai, **-cp out** giúp javac tra cứu lớp phụ thuộc đã được biên dịch; còn **-d out** chỉ định nơi ghi Main.class mới. Hai tùy chọn có cùng giá trị ở đây nhưng khác vai trò. Compiler classpath và runtime classpath là hai cấu hình được truyền cho hai chương trình khác nhau; đừng cho rằng cài đúng một bên tự động sửa được bên kia.

### Tìm .java phụ thuộc với -sourcepath

Cũng từ CWD = package-lab, ta có thể chỉ truyền Main.java và chỉ định nơi javac tìm các tệp nguồn phụ thuộc:

~~~sh
javac -encoding UTF-8 --release 17 -sourcepath src -d out src/com/example/app/Main.java
java -cp out com.example.app.Main
~~~

Khi cần định nghĩa Greeter và chưa có class tương ứng thích hợp, javac có thể tìm src/com/example/text/Greeter.java rồi biên dịch nguồn cần thiết. Lệnh này chạy được với hai lớp mẫu.

| Tùy chọn | Hỏi về loại đường dẫn nào? |
| --- | --- |
| -sourcepath src | Gốc để compiler tìm **nguồn .java** phụ thuộc |
| -cp out (khi dùng với javac) | Gốc/JAR để compiler tìm **lớp đã biên dịch** và thư viện |
| -d out | Gốc để compiler **ghi .class mới** |
| -cp out (khi dùng với java) | Gốc/JAR để **JVM** tìm các lớp lúc chạy |

Trong bài nhập môn, truyền tường minh cả hai file như phần 4 là cách dễ kiểm soát nhất. Với build nhiều nguồn, hãy để build tool quản lý source sets, classpath và thứ tự biên dịch.

## 8. Package trong mã nguồn và đường dẫn tệp có quan hệ gì?

Giả sử tệp vẫn nằm tại src/com/example/app/Main.java nhưng khai báo đầu tệp bị đổi thành:

~~~java
package com.example.other;
~~~

Khi cung cấp **đường dẫn file nguồn tường minh** cùng -d out, javac có thể vẫn biên dịch: tên lớp theo khai báo là com.example.other.Main và bytecode sẽ thuộc out/com/example/other/Main.class. Lúc này tên com.example.app.Main không còn chỉ đúng lớp vừa biên dịch.

Điều đó minh họa hai nguyên tắc:

- Package **khai báo trong mã** xác định tên lớp Java; đường dẫn vật lý đến tệp nguồn là quy ước tổ chức và một phần của chiến lược tìm nguồn.
- Vì -sourcepath, IDE và build tool dựa vào cấu trúc package để tìm tệp, việc giữ hai thứ nhất quán là rất quan trọng.

Sau khi khôi phục mã đúng, bảo đảm không còn dùng nhầm bản Main.class cũ nằm dưới một package khác.

Một vấn đề khác là tên public top-level class không khớp tên file. Nếu viết public class Program trong Main.java, javac sẽ yêu cầu đặt lớp công khai đó trong tệp Program.java. Không nên nhầm quy tắc tên tệp này với quy tắc ánh xạ package khi xuất bytecode.

## 9. Những lỗi điển hình khi đứng sai gốc

### Lỗi A — javac báo “file not found”

Ví dụ: terminal đứng ở package-lab/src nhưng lại chạy:

~~~sh
javac -d ../out src/com/example/app/Main.java
~~~

Đường dẫn tương đối khiến javac tìm package-lab/src/src/com/example/app/Main.java. Hãy bỏ tiền tố src/ hoặc chuyển về package-lab trước khi dùng lệnh ở phần 4.

Cách kiểm tra: trước tiên nhìn CWD, sau đó xác minh file thực sự tồn tại ở đường dẫn được truyền cho compiler. Đây là lỗi chọn đường dẫn nguồn, chưa phải lỗi cú pháp Java.

### Lỗi B — “package ... does not exist” hoặc “cannot find symbol”

Main import Greeter, nhưng compiler không nhìn thấy Greeter.java/Greeter.class qua những đường dẫn đầu vào hoặc cấu hình tìm lớp. Với ví dụ đơn giản, liệt kê rõ cả Greeter.java và Main.java trong cùng lệnh biên dịch; hoặc biên dịch Greeter trước rồi dùng -cp out để biên dịch Main.

Cũng phải kiểm tra tên package trong import và đầu file Greeter có đúng chính tả, kể cả chữ hoa/chữ thường.

### Lỗi C — “Could not find or load main class”

Nếu dùng:

~~~sh
java -cp out Main
~~~

JVM sẽ không tìm đúng com.example.app.Main. Dùng tên đầy đủ và classpath gốc:

~~~sh
java -cp out com.example.app.Main
~~~

Một lỗi tương tự xuất hiện nếu đặt classpath tới out/com/example/app hoặc đứng ở src mà vẫn truyền -cp out (khi thực tế out nằm tại ../out).

### Lỗi D — “NoClassDefFoundError”

Biên dịch Main đã thành công nhưng runtime thiếu Greeter.class hoặc một dependency khác. Đây là lỗi nạp/liên kết lớp khi chạy; cần kiểm tra **runtime classpath**, tập .class thực tế và phiên bản JAR được dùng. Một lỗi có thể liên quan cả tên lớp không phù hợp vị trí mong đợi.

### Lỗi E — “UnsupportedClassVersionError”

Phiên bản bytecode mới hơn JVM đang chạy. Kiểm tra java -version và mức biên dịch. --release 17 giúp compiler nhắm class-file version của Java 17 và API platform Java 17; nó không tự đảm bảo mọi JAR ngoài đều tương thích.

### Lỗi F — Chạy ra nội dung cũ

Nếu sửa Main.java nhưng không biên dịch lại, JVM vẫn có thể chạy .class cũ. Sau một lần biên dịch thất bại, out cũng có thể còn chứa file từ lượt trước. Trong **dự án bài tập**, có thể xóa riêng out, tạo lại rồi biên dịch lại từ nguồn hiện tại để loại trừ kết quả giả. Không xóa các thư mục build lạ của dự án thật khi chưa biết cách công cụ build đang sử dụng chúng.

| Triệu chứng | Tầng bị lỗi | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| file not found: src/... | Đường dẫn tới nguồn | CWD và đường dẫn tương đối |
| package ... does not exist | Phân giải package lúc compile | Import, nguồn phụ thuộc, -sourcepath hoặc -cp |
| cannot find symbol | Phân giải tên/kiểu lúc compile | Tên lớp/phương thức, phụ thuộc, phạm vi |
| Could not find or load main class | Tìm lớp khởi động | Tên lớp đầy đủ, classpath root |
| NoClassDefFoundError | Nạp lớp lúc chạy | Runtime classpath, JAR/.class cần thiết |
| UnsupportedClassVersionError | Tương thích bytecode | JDK chạy và --release |

## 10. Dùng javap để xác minh lớp thực sự đã tạo

Từ CWD = package-lab, sau khi biên dịch thành công:

~~~sh
javap -classpath out com.example.app.Main
javap -classpath out com.example.text.Greeter
~~~

javap hiển thị tên đầy đủ và chữ ký của thành viên public. Phần có ý nghĩa của kết quả với Main:

~~~text
public final class com.example.app.Main {
  public static void main(java.lang.String[]);
}
~~~

Đầu ra thực tế còn có thể có dòng Compiled from "Main.java" ở phía trên. Với Greeter, bạn sẽ nhìn thấy phương thức public static java.lang.String greet(java.lang.String). Nhờ vậy bạn xác nhận được **tên lớp bytecode** mà không chỉ dựa vào đường dẫn nguồn.

Có thể xem metadata sâu hơn:

~~~sh
javap -classpath out -verbose com.example.app.Main
~~~

Với mã được biên dịch bằng --release 17, class-file **major version 61** tương ứng Java 17. Kiểm tra phiên bản là hữu ích, nhưng không thay thế việc xác minh dependencies và classpath khi chạy.

## 11. Dự án theo cấu trúc src/main/java

Các dự án dùng Maven/Gradle thường đặt mã tại src/main/java thay vì src:

~~~text
my-project/
├── src/
│   └── main/
│       └── java/
│           └── com/
│               └── example/
│                   └── app/
│                       └── Main.java
└── build/
    └── classes/
~~~

Nếu Main là một chương trình độc lập không cần source/dependency khác, đứng tại CWD = my-project và tạo trước build/classes, có thể dùng:

~~~sh
javac -encoding UTF-8 --release 17 -d build/classes src/main/java/com/example/app/Main.java
java -cp build/classes com.example.app.Main
~~~

Lệnh này minh họa việc thay đổi source root và output root; **Main của bài thực hành chính ở phần 3 phụ thuộc Greeter**, vì vậy nếu muốn dùng đúng hai lớp đó phải biên dịch cả hai nguồn hoặc cấu hình compiler tìm phụ thuộc tương ứng. Đừng hiểu ví dụ một tệp ở đây là một cách build đầy đủ mọi dự án thực.

Khi ứng dụng lớn có dependency ngoài, annotation processors, module-info.java, nhiều source set hoặc JAR, hãy dùng tác vụ build của Gradle/Maven. Kiến thức về CWD, source root và classpath root vẫn giúp đọc lỗi của các công cụ đó chính xác hơn.

## 12. Bài tập vận dụng

1. **Tự dự đoán đường dẫn.** Từ CWD = package-lab, đường dẫn tới Greeter.java là src/com/example/text/Greeter.java; từ CWD = package-lab/src, đường dẫn là com/example/text/Greeter.java. Giải thích lý do hai lệnh khác nhau.
2. **Biên dịch và chạy.** Tạo hai tệp như phần 3, biên dịch cả hai từ package-lab, chạy java -cp out com.example.app.Main và đối chiếu stdout Hello, Lan!.
3. **Đổi dữ liệu.** Thay "Lan" thành "Minh", biên dịch lại và chạy. Stdout phải là Hello, Minh!. Nếu không thay đổi, tìm .class cũ hoặc kiểm tra bạn đang ở nhầm CWD.
4. **Đổi vị trí terminal.** Chạy từ package-lab/src với -d ../out và -cp ../out, giữ nguyên tên lớp com.example.app.Main. Tự giải thích ba khái niệm không đổi: package, tên lớp và logic chương trình.
5. **Thử compile riêng.** Chỉ biên dịch Greeter, rồi biên dịch Main với -cp out. Chỉ ra lý do -cp và -d không có cùng chức năng dù cùng nhận out.
6. **Sai package có chủ đích.** Tạm đổi package của Main thành com.example.other. Quan sát nơi javac tạo .class với -d out, dự đoán tên lớp cần dùng khi java chạy, rồi hoàn nguyên nguồn.
7. **Đọc bytecode.** Dùng javap -classpath out com.example.app.Main, đối chiếu tên đầy đủ với package trong nguồn và thư mục .class trong out.

## 13. Checklist trước khi kết luận đúng

- CWD được kiểm tra rõ bằng pwd hoặc Get-Location.
- Đường dẫn tới mỗi file .java được tính từ CWD và tồn tại trên đĩa.
- Dòng package trong nguồn khớp quy ước nhánh thư mục dưới source root.
- Public top-level class có tên file tương ứng.
- Output root đã tồn tại trước khi dùng javac -d.
- Các lớp/phụ thuộc cần thiết đều được compiler nhìn thấy.
- JVM dùng classpath trỏ đến **gốc của cây package .class**.
- java nhận tên lớp đầy đủ, ví dụ com.example.app.Main.
- .class vừa được tạo từ mã hiện tại, không phải artifact cũ.

Có thể nhớ ba ánh xạ:

~~~text
CWD + đường dẫn tương đối      → File nguồn .java
Output root + đường dẫn package → File đã biên dịch .class
Classpath root + tên lớp đầy đủ → Lớp JVM cần nạp
~~~

Khi ba ánh xạ này nhất quán, biên dịch chương trình Java nhiều package từ gốc dự án hoặc từ gốc mã nguồn đều đúng. Điểm cốt lõi không nằm ở một vị trí terminal cố định mà nằm ở việc hiểu **đường dẫn nguồn**, **tên package** và **classpath** làm việc cùng nhau như thế nào.
