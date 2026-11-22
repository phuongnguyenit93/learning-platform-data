# Tạo chương trình Java tối thiểu và thực hiện checkpoint–restore

Bài thực hành này tạo một chương trình Java nhỏ, đăng ký callback CRaC, chạy chương trình trên JDK có hỗ trợ CRaC, tạo checkpoint image rồi khởi chạy lại tiến trình từ image đó.

Chương trình in PID và một bộ đếm tăng dần. Khi checkpoint, callback beforeCheckpoint() in thông báo. Khi restore, callback afterRestore() in thông báo khác và vòng lặp tiếp tục với giá trị bộ đếm đã có trước checkpoint.

Bài thực hành dùng jcmd để người học nhìn rõ ba thao tác: chạy ứng dụng, tạo checkpoint và restore. Các lệnh dưới đây dành cho môi trường Linux có JDK CRaC và các điều kiện kernel/runtime mà bản phân phối yêu cầu.

## 1. Kết quả mong đợi

~~~text
Biên dịch chương trình
       |
       v
Khởi chạy bằng JDK CRaC
       |
       v
Ứng dụng in PID và tick tăng dần
       |
       v
jcmd <pid> JDK.checkpoint
       |
       v
beforeCheckpoint() được gọi
       |
       v
Runtime ghi checkpoint image
       |
       v
Tiến trình gốc kết thúc sau checkpoint thành công
       |
       v
java -XX:CRaCRestoreFrom=<image>
       |
       v
afterRestore() được gọi
       |
       v
Bộ đếm tiếp tục từ trạng thái đã checkpoint
~~~

Khi thực hành thành công, bạn sẽ quan sát được:

- Một checkpoint image được tạo ở thư mục chỉ định.
- beforeCheckpoint() chạy trước khi runtime lưu trạng thái.
- Tiến trình được khôi phục từ image.
- afterRestore() chạy trong tiến trình đã restore.
- Biến counter tiếp tục tăng từ giá trị trước checkpoint thay vì quay lại 0.

Checkpoint image lưu trạng thái tiến trình theo khả năng của JDK CRaC và cơ chế checkpoint/restore bên dưới. Nó không phải bản sao lưu toàn bộ máy hoặc filesystem.

## 2. Chuẩn bị môi trường

Bạn cần:

- Một bản phân phối JDK có hỗ trợ CRaC.
- Phiên bản JDK tương thích với CRaC API được dùng để biên dịch.
- Maven 3.x.
- Môi trường Linux đáp ứng yêu cầu kernel, CRIU, quyền và cấu hình container của bản phân phối JDK.
- Quyền chạy jcmd với cùng user sở hữu JVM.
- Một thư mục riêng để lưu checkpoint image.

CRaC cần hỗ trợ từ runtime và môi trường hệ điều hành. Cài thư viện API vào một JDK thông thường không tự biến JDK đó thành JDK có khả năng checkpoint/restore.

### Kiểm tra JDK và Maven

~~~bash
java -version
javac -version
jcmd -l
mvn -version
~~~

Hãy xác nhận java, javac và jcmd đến từ cùng một JDK CRaC. Nếu PATH trỏ đến nhiều JDK khác nhau, dùng đường dẫn tuyệt đối đến thư mục bin của bản phân phối cần thử.

Các yêu cầu về CRIU, kernel, quyền và container thay đổi theo bản phân phối. Đọc hướng dẫn cài đặt của JDK CRaC đang dùng trước khi chạy checkpoint. Không mặc định rằng mọi container Linux hoặc mọi môi trường WSL đều đáp ứng các yêu cầu đó.

## 3. Tạo cấu trúc dự án

Tạo một dự án Maven tối thiểu:

~~~text
crac-minimal/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── cracdemo/
                        └── Main.java
~~~

Có thể tạo thư mục bằng shell:

~~~bash
mkdir -p crac-minimal/src/main/java/com/example/cracdemo
cd crac-minimal
~~~

Checkpoint directory sẽ nằm ngoài target/ của Maven. Như vậy, lệnh mvn clean không xóa nhầm image dùng cho lần restore.

## 4. Khai báo CRaC API trong Maven

Tạo file pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>crac-minimal</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.crac</groupId>
            <artifactId>crac</artifactId>
            <version>1.4.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

org.crac:crac cung cấp các kiểu API như Core, Resource và Context. Phiên bản 1.4.0 là phiên bản ví dụ để ghim dependency và giúp dự án biên dịch lặp lại. Khi làm việc với một JDK CRaC cụ thể, chọn phiên bản API được bản phân phối đó hỗ trợ.

maven.compiler.release đặt mức ngôn ngữ Java mục tiêu. Nếu JDK CRaC của bạn dùng Java 21, có thể đổi giá trị thành 21 sau khi xác nhận phiên bản Maven compiler và API tương thích.

## 5. Viết chương trình Java tối thiểu

Tạo src/main/java/com/example/cracdemo/Main.java:

~~~java
package com.example.cracdemo;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class Main {

    public static void main(String[] args) throws InterruptedException {
        Core.getGlobalContext().register(new DemoResource());

        long counter = 0;

        System.out.println(
            "[APP] started; pid=" + ProcessHandle.current().pid()
        );
        System.out.flush();

        while (true) {
            counter++;

            System.out.println("[APP] tick=" + counter);
            System.out.flush();

            Thread.sleep(1_000);
        }
    }

    private static final class DemoResource implements Resource {

        @Override
        public void beforeCheckpoint(
                Context<? extends Resource> context) {
            System.out.println("[CRAC] beforeCheckpoint");
            System.out.flush();
        }

        @Override
        public void afterRestore(
                Context<? extends Resource> context) {
            System.out.println("[CRAC] afterRestore");
            System.out.flush();
        }
    }
}
~~~

### Giải thích chương trình

Core.getGlobalContext() trả về context CRaC toàn cục. Gọi register() để đăng ký một Resource với runtime.

Resource có hai callback:

- beforeCheckpoint(): được gọi khi runtime chuẩn bị tạo checkpoint. Ứng dụng dùng callback này để đưa tài nguyên về trạng thái an toàn.
- afterRestore(): được gọi sau khi tiến trình được khôi phục. Ứng dụng dùng callback này để mở lại hoặc xác minh tài nguyên cần thiết.

Trong bài thực hành, callback chỉ in thông báo để dễ quan sát. Chương trình không giữ database connection, socket hoặc file handle bên ngoài nên không cần logic đóng/mở lại các tài nguyên đó.

Biến counter là biến cục bộ trong main(). Khi checkpoint, trạng thái thread và stack của tiến trình được lưu theo khả năng runtime. Sau restore, vòng lặp tiếp tục với trạng thái đã lưu. Đây là điểm quan sát giúp phân biệt restore với khởi động một JVM mới từ đầu.

ProcessHandle.current().pid() chỉ để hiển thị PID của tiến trình. Không giả định PID trước và sau restore phải giống nhau; điều đó phụ thuộc môi trường và cách runtime thực hiện restore.

## 6. Biên dịch và chuẩn bị dependency

Từ thư mục gốc dự án:

~~~bash
mvn clean package
mvn dependency:copy-dependencies \
  -DincludeScope=runtime \
  -DoutputDirectory=target/dependency
~~~

Sau khi hoàn tất, các file cần dùng gồm:

~~~text
target/classes/com/example/cracdemo/Main.class
target/dependency/crac-<version>.jar
~~~

Nếu Maven không tải được dependency, kiểm tra repository access và phiên bản org.crac:crac đã khai báo. Không đổi sang một JDK khác chỉ để bỏ qua lỗi biên dịch mà chưa xác nhận runtime đó hỗ trợ CRaC.

## 7. Khởi chạy chương trình với checkpoint directory

Dùng một thư mục checkpoint mới và có đường dẫn rõ ràng. Ví dụ Linux:

~~~bash
mkdir -p /tmp/crac-minimal-checkpoint
~~~

Nếu thư mục đã chứa image từ lần thử trước, hãy chọn một thư mục khác hoặc dọn artifact cũ sau khi xác nhận không còn tiến trình restore sử dụng nó. Tránh ghi đè một image đang được dùng.

Khởi chạy ứng dụng:

~~~bash
java \
  -XX:CRaCCheckpointTo=/tmp/crac-minimal-checkpoint \
  -cp "target/classes:target/dependency/*" \
  com.example.cracdemo.Main
~~~

Ứng dụng sẽ in PID và các dòng tick:

~~~text
[APP] started; pid=24180
[APP] tick=1
[APP] tick=2
[APP] tick=3
[APP] tick=4
~~~

Giữ terminal này mở để quan sát log. Ghi lại PID hiển thị ở dòng [APP] started.

CRaCCheckpointTo chỉ định vị trí runtime ghi checkpoint image. Tùy bản phân phối, runtime có thể cần các file phụ trợ hoặc điều kiện filesystem riêng; dùng thư mục dành riêng cho lần thử và không chỉnh sửa nội dung image bằng tay.

## 8. Tạo checkpoint bằng jcmd

Mở terminal Linux thứ hai, chuyển đến thư mục dự án và dùng PID đã ghi:

~~~bash
jcmd 24180 JDK.checkpoint
~~~

Thay 24180 bằng PID thật của chương trình.

Nếu cần, dùng đường dẫn đầy đủ đến jcmd thuộc cùng JDK CRaC đang chạy ứng dụng:

~~~bash
/path/to/crac-jdk/bin/jcmd 24180 JDK.checkpoint
~~~

Khi callback được gọi, terminal chạy ứng dụng sẽ có dòng:

~~~text
[CRAC] beforeCheckpoint
~~~

Sau khi checkpoint thành công, runtime ghi trạng thái tiến trình vào checkpoint directory. Với luồng checkpoint được kích hoạt từ jcmd, tiến trình gốc thường kết thúc sau khi checkpoint hoàn tất; hãy xác nhận kết quả lệnh và log runtime của bản phân phối đang dùng.

Không copy hoặc restore image khi lệnh checkpoint vẫn đang chạy. Chờ thao tác kết thúc và xác nhận runtime báo thành công.

### Kiểm tra tiến trình và image

Có thể kiểm tra JVM còn chạy hay không:

~~~bash
jcmd -l
~~~

Kiểm tra thư mục image:

~~~bash
du -sh /tmp/crac-minimal-checkpoint
find /tmp/crac-minimal-checkpoint -maxdepth 2 -type f
~~~

Cấu trúc file bên trong checkpoint directory là chi tiết triển khai của runtime. Không đổi tên, xóa hoặc sửa file bên trong để thử nghiệm nếu chưa có hướng dẫn của bản phân phối.

## 9. Restore từ checkpoint image

Sau khi checkpoint thành công, khởi chạy restore bằng chính JDK CRaC tương thích:

~~~bash
java \
  -XX:CRaCRestoreFrom=/tmp/crac-minimal-checkpoint
~~~

CRaCRestoreFrom yêu cầu runtime khôi phục tiến trình từ image đã tạo. Runtime sử dụng trạng thái lệnh và process đã lưu trong checkpoint; cách gọi chi tiết có thể phụ thuộc bản phân phối.

Kết quả mong đợi trong output của tiến trình đã restore:

~~~text
[CRAC] afterRestore
[APP] tick=5
[APP] tick=6
[APP] tick=7
~~~

Giá trị tick cụ thể phụ thuộc thời điểm bạn tạo checkpoint. Điều cần quan sát là bộ đếm tiếp tục từ giá trị đã lưu. Chương trình không chạy lại main() từ đầu như một lần khởi động thông thường; tiến trình được khôi phục từ trạng thái checkpoint.

Nếu afterRestore() không xuất hiện, hãy xem log runtime và lỗi restore. Đừng coi việc lệnh Java vừa khởi chạy là bằng chứng restore đã thành công.

## 10. Hiểu thứ tự callback trong bài thực hành

Trong ví dụ, thứ tự quan sát được là:

~~~text
Khởi chạy JVM
    |
    v
Đăng ký DemoResource
    |
    v
Vòng lặp tick chạy
    |
    v
jcmd yêu cầu checkpoint
    |
    v
DemoResource.beforeCheckpoint()
    |
    v
Runtime tạo checkpoint image
    |
    v
Khởi chạy restore
    |
    v
DemoResource.afterRestore()
    |
    v
Vòng lặp tick tiếp tục
~~~

beforeCheckpoint() là nơi chuẩn bị tài nguyên trước khi lưu trạng thái. Ví dụ thực tế có thể dừng nhận request, drain worker, flush dữ liệu và đóng socket.

afterRestore() là nơi tạo lại tài nguyên bên ngoài hoặc xác minh chúng còn dùng được. Ví dụ thực tế có thể lấy credential mới, tạo database pool, mở file channel và chỉ đánh dấu ứng dụng READY khi dependency đã hoạt động.

Không đặt toàn bộ công việc nặng vào constructor hoặc giả định @PostConstruct tự chạy lại sau restore. Restore phục hồi process state; nó không mặc định tạo một ApplicationContext mới.

## 11. Thử nghiệm thêm: đóng và mở lại một file

Sau khi bài cơ bản chạy thành công, có thể mở rộng chương trình để quản lý một file bằng Resource. Ví dụ dưới đây minh họa cách đóng FileChannel trước checkpoint và mở lại sau restore.

~~~java
package com.example.cracdemo;

import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class FileResource implements Resource {
    private final Path path;
    private FileChannel channel;

    public FileResource(Path path) throws IOException {
        this.path = path.toAbsolutePath().normalize();
        openChannel();
        Core.getGlobalContext().register(this);
    }

    private void openChannel() throws IOException {
        channel = FileChannel.open(
            path,
            StandardOpenOption.CREATE,
            StandardOpenOption.READ,
            StandardOpenOption.WRITE
        );
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (channel != null && channel.isOpen()) {
            channel.force(true);
            channel.close();
            channel = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        openChannel();
    }

    public synchronized FileChannel channel() {
        if (channel == null || !channel.isOpen()) {
            throw new IllegalStateException("File channel is not open");
        }
        return channel;
    }
}
~~~

Để dùng lớp này, tạo file trong thư mục dữ liệu được mount và truyền path vào constructor. Bảo đảm thư mục đó tồn tại và có quyền ghi trước khi khởi chạy.

Ví dụ này chỉ minh họa lifecycle. Ứng dụng thật cần đồng bộ writer trước checkpoint, lưu offset đã commit, xác minh file identity sau restore và xử lý lỗi nếu file bị thay thế hoặc truncate. Nếu checkpoint bị hủy sau khi channel đã đóng, tiến trình gốc cũng cần mở lại channel; afterRestore() không phải callback rollback cho checkpoint thất bại.

Không mở file trong ví dụ rồi giả định mọi filesystem, descriptor hoặc file lock đều được CRaC hỗ trợ giống nhau. Kiểm thử với đúng filesystem và runtime triển khai.

## 12. Thử nghiệm checkpoint từ bên trong chương trình

CRaC API cũng cung cấp Core.checkpointRestore() để ứng dụng chủ động yêu cầu checkpoint và restore. Cách này khác với việc gửi lệnh jcmd từ một terminal bên ngoài.

Khung gọi:

~~~java
try {
    Core.checkpointRestore();

    // Tiến trình đã đi qua checkpoint và restore thành công.
    System.out.println("[APP] checkpointRestore returned after restore");

} catch (org.crac.CheckpointException checkpointFailure) {
    // Checkpoint thất bại; tiến trình ban đầu cần phục hồi resource
    // mà beforeCheckpoint() đã đóng hoặc thay đổi.
    throw checkpointFailure;

} catch (org.crac.RestoreException restoreFailure) {
    // Restore gặp lỗi; không mở traffic nếu resource chưa sẵn sàng.
    throw restoreFailure;
}
~~~

Khi dùng API này, ứng dụng có thể xử lý CheckpointException trong luồng gọi và phục hồi tài nguyên của tiến trình gốc. Nếu checkpoint được kích hoạt bằng jcmd từ bên ngoài, luồng ứng dụng không có catch block bao quanh lời gọi đó.

Không gọi Core.checkpointRestore() trong vòng lặp tick mỗi giây. Hãy kích hoạt một lần theo điều kiện kiểm thử rõ ràng, vì thao tác này thay đổi luồng thực thi của toàn bộ tiến trình.

## 13. So sánh với khởi động JVM thông thường

Để thấy sự khác nhau, chạy chương trình không có tùy chọn checkpoint:

~~~bash
java \
  -cp "target/classes:target/dependency/*" \
  com.example.cracdemo.Main
~~~

Lần chạy này bắt đầu counter từ 0 và không tạo checkpoint image. Trên JDK thường, API CRaC có thể cho phép biên dịch hoặc chạy một số logic ứng dụng, nhưng điều đó không chứng minh runtime có khả năng checkpoint/restore. Chỉ thực hiện bài thực hành checkpoint bằng JDK CRaC được hỗ trợ.

Khi so sánh hiệu năng, đo đến cùng một mốc, chẳng hạn lúc ứng dụng thực sự READY. Không so sánh thời gian JVM resume với thời gian cold startup đã bao gồm mở kết nối database và warm-up.

## 14. Xử lý lỗi thường gặp

### JVM không nhận tùy chọn CRaC

Dấu hiệu: JVM báo unrecognized VM option hoặc tùy chọn không được hỗ trợ.

Nguyên nhân thường gặp: đang dùng JDK không có CRaC hoặc PATH trỏ nhầm JDK.

Cách xử lý:

- Kiểm tra java -version.
- Dùng đường dẫn tuyệt đối đến JDK CRaC.
- Kiểm tra java, javac và jcmd cùng bản phân phối.
- Đọc hướng dẫn của vendor về cờ checkpoint/restore.

### jcmd không tìm thấy process

Dấu hiệu: jcmd -l không liệt kê PID hoặc lệnh attach thất bại.

Kiểm tra:

- PID có đúng không.
- JVM còn chạy không.
- jcmd có thuộc cùng JDK không.
- User chạy jcmd có quyền attach vào process không.
- JVM có tắt Attach Listener hoặc giới hạn attach không.

### Checkpoint thất bại do môi trường

Nguyên nhân có thể là CRIU, kernel, permission, container capability, mount hoặc resource đang mở không được hỗ trợ.

Cách xử lý:

- Đọc exception và log runtime đầy đủ.
- Kiểm tra yêu cầu của JDK CRaC distribution.
- Thử chương trình tối thiểu không có socket hoặc native resource.
- Xác minh checkpoint directory và filesystem.
- Không cấp quyền privileged rộng cho container chỉ để che lỗi; xác định đúng capability mà runtime yêu cầu.

### Restore không tìm thấy image

Kiểm tra đường dẫn của CRaCRestoreFrom, quyền đọc và việc checkpoint đã hoàn tất. Dùng đường dẫn tuyệt đối để tránh nhầm working directory.

### Restore thất bại do runtime khác

Tạo và restore image bằng JDK/CRaC tương thích. Không giả định image có thể chuyển tự do giữa các vendor, build, kiến trúc CPU hoặc môi trường kernel.

### afterRestore() không chạy

Nếu runtime chưa khôi phục được process đến mức thực thi Java, callback ứng dụng không thể chạy. Kiểm tra log runtime trước khi kết luận callback bị bỏ qua.

### Resource mở lại thất bại

Nếu database, file hoặc client không mở được, giữ ứng dụng ở trạng thái not-ready. Kiểm tra mount, quyền, DNS, network, credential và dependency trước khi mở request gate.

## 15. Thực hành trong container hoặc môi trường Windows

Các ví dụ lệnh trong bài dùng Bash trên Linux. CRaC thường dựa vào các tính năng checkpoint/restore của Linux và CRIU; hỗ trợ cụ thể tùy JDK distribution, kernel và runtime container.

Nếu máy phát triển chạy Windows:

- Không giả định java -XX:CRaCCheckpointTo=... chạy được trong PowerShell với một JDK Windows thông thường.
- Dùng Linux VM hoặc môi trường Linux được vendor CRaC hỗ trợ.
- Chỉ dùng WSL2 khi kernel, CRIU, quyền và bản phân phối JDK thực sự đáp ứng yêu cầu.
- Nếu chạy trong container, kiểm tra mount, namespace, capability và quyền cần thiết theo tài liệu runtime.
- Giữ checkpoint image trên filesystem phù hợp và có đủ dung lượng.

Không copy checkpoint image từ Linux sang một môi trường khác rồi mặc định restore được. Image phụ thuộc vào runtime và trạng thái hệ thống ở mức thấp hơn bytecode Java.

## 16. Dọn môi trường sau khi thực hành

Sau khi đã hoàn tất restore và dừng chương trình, có thể xóa thư mục checkpoint thử nghiệm:

~~~bash
rm -rf -- /tmp/crac-minimal-checkpoint
~~~

Chỉ chạy lệnh trên khi đã xác nhận đúng đường dẫn dành riêng cho bài thực hành và không còn restore operation sử dụng image. Không dùng wildcard rộng như /tmp/* để dọn checkpoint.

Nếu muốn giữ lại để thực hành nhiều lần, lưu image cùng metadata về JDK, CRaC runtime, kernel và kiến trúc đã tạo nó. Không xem image thử nghiệm là artifact có thể triển khai production.

## 17. Bài tập mở rộng

Sau khi chương trình tối thiểu hoạt động, có thể thử:

1. Thêm một Resource thứ hai và ghi log thứ tự callback.
2. Thêm FileChannel và kiểm tra dữ liệu đã flush trước checkpoint.
3. Thử tạo lỗi trong beforeCheckpoint() rồi quan sát checkpoint thất bại.
4. Thử tạo lỗi trong afterRestore() và giữ request gate đóng.
5. Thêm một dependency HTTP hoặc database trong môi trường test và tạo lại client sau restore.
6. Đo thời gian từ lúc gọi jcmd đến callback afterRestore().
7. Đo riêng thời gian mở lại từng resource.
8. So sánh cold startup với restore trên cùng mốc READY.
9. Thử restore trên môi trường có filesystem hoặc quyền khác và ghi lại lỗi.
10. Tạo checkpoint mới sau khi ứng dụng đã restore thành công.

Mỗi bài tập nên dùng checkpoint directory riêng. Ghi lại JDK build, runtime, kernel và kết quả để có thể tái hiện.

## 18. Nguyên tắc cần ghi nhớ

- Cần JDK CRaC và môi trường hệ điều hành được hỗ trợ; dependency API đơn thuần không cung cấp khả năng checkpoint.
- Đăng ký Resource bằng Core.getGlobalContext().register(...).
- beforeCheckpoint() chuẩn bị tài nguyên trước khi runtime lưu trạng thái.
- afterRestore() mở lại hoặc xác minh tài nguyên trong tiến trình đã khôi phục.
- Dùng -XX:CRaCCheckpointTo để chỉ định checkpoint directory.
- Dùng jcmd <pid> JDK.checkpoint để yêu cầu checkpoint từ bên ngoài.
- Dùng -XX:CRaCRestoreFrom để restore image.
- Chờ checkpoint hoàn tất trước khi copy hoặc restore image.
- Dùng cùng JDK/CRaC tương thích và kiểm tra kernel, CRIU, mount, permission.
- Quan sát trạng thái ứng dụng và readiness; process tồn tại chưa đủ chứng minh đã phục vụ được.
- Nếu callback đóng resource rồi checkpoint thất bại, tiến trình gốc cần có đường phục hồi.
- Nếu afterRestore() thất bại, giữ ứng dụng not-ready.
- Checkpoint image là artifact phụ thuộc môi trường, không phải file JAR portable.

Bài thực hành tối thiểu cho thấy CRaC lưu và khôi phục trạng thái của một tiến trình đang chạy. Khi đã quan sát được callback trước checkpoint, callback sau restore và bộ đếm tiếp tục từ giá trị cũ, bạn có nền tảng để mở rộng sang database pool, HTTP client, file handle và các tài nguyên thực tế của ứng dụng.
