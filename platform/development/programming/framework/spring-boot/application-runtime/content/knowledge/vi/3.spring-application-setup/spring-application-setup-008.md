# Chế độ headless và khi ứng dụng Spring Boot cần tương tác đồ họa

## 1. Headless nghĩa là gì?

Trong Java, **headless** là chế độ hoạt động không dựa vào màn hình, bàn phím hoặc chuột để hiển thị và tương tác với các cửa sổ đồ họa AWT/Swing. Đặc biệt, các API yêu cầu thiết bị hiển thị (JFrame, JDialog, lấy kích thước màn hình, thao tác chuột...) không phù hợp với chế độ này.

**SpringApplication mặc định headless=true.** Đây là lựa chọn hợp lý với backend Spring Boot trên server, container, máy CI hoặc ứng dụng xử lý lô: chúng thường phục vụ HTTP, dữ liệu và các tác vụ nền, không cần mở cửa sổ trên máy chạy JVM.

Cần tránh ba hiểu lầm:

- **Headless không có nghĩa “không có giao diện web”**. Một REST API Spring Boot headless vẫn phục vụ giao diện React, HTML, ảnh và dữ liệu cho trình duyệt của người dùng.
- **Headless không có nghĩa “không thể xử lý đồ họa”**. Java vẫn có thể tạo BufferedImage, vẽ bằng Graphics2D rồi lưu bằng ImageIO mà không mở cửa sổ.
- **Headless không quyết định ứng dụng chạy một lần hay lâu dài**. Một job tạo PNG xong rồi kết thúc và một web service luôn phục vụ yêu cầu đều có thể headless.

Câu hỏi cần trả lời là: **chính tiến trình Java có phải mở cửa sổ AWT/Swing để người dùng tương tác trực tiếp trên máy đó không?** Nếu không, thông thường cứ giữ headless.

## 2. Các tác vụ được hỗ trợ và bị hạn chế

| Tác vụ | Khi headless=true | Vì sao |
| --- | --- | --- |
| Xử lý HTTP, DB, queue, REST API, CLI, batch job | Hoạt động | Không phụ thuộc màn hình AWT |
| Đọc/ghi tệp, lập lịch, gọi API bên ngoài | Hoạt động | Không có yêu cầu về GUI |
| BufferedImage và Graphics2D vẽ vào bộ nhớ | Hoạt động | Vùng vẽ là dữ liệu pixel trong RAM |
| ImageIO đọc/ghi PNG, JPEG | Hoạt động | Không phải mở cửa sổ |
| Vẽ chữ lên ảnh bằng Font | Có thể hoạt động | Cần font và runtime phù hợp, dù không cần màn hình |
| JFrame, JDialog, JWindow, JFileChooser hiển thị cửa sổ | Không | Cần hạ tầng hiển thị tương tác |
| Toolkit.getScreenSize(), java.awt.Robot | Không | Phụ thuộc thiết bị màn hình hoặc input |
| Cung cấp trang web để trình duyệt hiển thị | Hoạt động | Browser phía client thực hiện hiển thị |

Khi code cố dùng các API phụ thuộc GUI trong chế độ headless, Java thường ném **java.awt.HeadlessException**. Đây không phải lỗi Spring bean hay HTTP: nó cho biết môi trường đồ họa AWT không phù hợp cho thao tác được yêu cầu.

## 3. SpringApplication thiết lập chế độ headless

Khi khởi tạo SpringApplication, có thể gọi setter trước khi chạy:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setHeadless(true);
app.run(args);
~~~

Muốn chạy một công cụ desktop có Swing/AWT:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setHeadless(false);
app.run(args);
~~~

Hai đoạn này minh họa cấu hình đặt trong main; **MyApplication** là tên thay thế cho lớp Spring Boot thực tế. Hai ví dụ hoàn chỉnh ở phần sau sử dụng tên lớp có thật.

**Các quy tắc cần nhớ:**

1. SpringApplication mặc định **headless=true**. Trong Spring Boot 3.x, API **setHeadless(boolean)** dùng để chỉ định chế độ này.
2. Java sử dụng **system property java.awt.headless**; có thể chỉ định ngay khi khởi động JVM:

~~~bash
java -Djava.awt.headless=true -jar app.jar
java -Djava.awt.headless=false -jar desktop-app.jar
~~~

3. Nếu thuộc tính **java.awt.headless** đã được khai báo tường minh bởi tham số **-D**, giá trị đó có thể được ưu tiên so với mặc định của SpringApplication. Khi kiểm tra sự cố, đối chiếu cả cấu hình JVM và mã **setHeadless(...)**.
4. **Thiết lập phải diễn ra sớm**, trước lần khởi tạo AWT Toolkit/GraphicsEnvironment hoặc các component đồ họa. Thay thuộc tính sau khi AWT đã khởi tạo có thể không thay đổi trạng thái đã được xác định hoặc cache.
5. **setHeadless(false) không tự cung cấp một màn hình.** Nếu server/container không có môi trường desktop hoặc display server phù hợp, tạo cửa sổ vẫn có thể lỗi.

Có thể đọc trạng thái Java AWT bằng:

~~~java
boolean headless = java.awt.GraphicsEnvironment.isHeadless();
~~~

Nếu kết quả là **true**, thao tác cần màn hình sẽ không sử dụng được. Nếu kết quả là **false**, vẫn phải kiểm tra khả năng truy cập display thực tế: việc ép một system property về false không biến máy chủ thành desktop.

### Tách biệt với WebApplicationType

| WebApplicationType | Headless | Ví dụ |
| --- | --- | --- |
| SERVLET hoặc REACTIVE | true | Backend HTTP thông thường, API sinh ảnh |
| NONE | true | CLI xuất báo cáo, job xử lý tệp, trình xử lý lô |
| NONE | false | Ứng dụng desktop dùng Swing/AWT |
| SERVLET hoặc REACTIVE | false | Ứng dụng đặc thù vừa mở web server vừa có GUI cục bộ |

**WebApplicationType.NONE** chỉ yêu cầu Spring Boot không khởi động web server. Nó không tự làm JVM headless. Ngược lại, một dịch vụ HTTP có thể chạy **headless=true** hoàn toàn bình thường. Đừng nhầm **java.awt.headless** với **server.port** hoặc **spring.main.web-application-type**.

## 4. Thí nghiệm với JDK 17+: đọc trạng thái headless

Tạo một tệp **HeadlessProbe.java**:

~~~java
import java.awt.GraphicsEnvironment;

public class HeadlessProbe {
    public static void main(String[] args) {
        System.out.println("headless=" + GraphicsEnvironment.isHeadless());
    }
}
~~~

Biên dịch bằng JDK 17+ có module **java.desktop** rồi chạy:

~~~bash
javac HeadlessProbe.java
java -Djava.awt.headless=true HeadlessProbe
~~~

**Stdout chính xác:**

~~~text
headless=true
~~~

Thử thay đổi tham số JVM:

~~~bash
java -Djava.awt.headless=false HeadlessProbe
~~~

Khi không có thứ gì khác thay đổi thuộc tính, stdout là:

~~~text
headless=false
~~~

Đây là chương trình JDK thuần, không phụ thuộc Spring. Nó chứng minh **java.awt.headless** là cấu hình của Java AWT; đừng suy ra rằng in **false** luôn đồng nghĩa có cửa sổ khả dụng trên Linux server không có X11.

## 5. Ví dụ Spring Boot tạo ảnh PNG trong chế độ headless

Job tạo ảnh báo cáo là một ví dụ điển hình: cần xử lý pixel nhưng không cần GUI. Chương trình dưới đây là **một dự án Spring Boot 3.x độc lập**, Java 17+, đã có dependency **spring-boot-starter** và plugin chạy Spring Boot. Đặt mã tại **src/main/java/example/HeadlessRenderApplication.java**.

~~~java
package example;

import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.GraphicsEnvironment;
import java.awt.image.BufferedImage;
import java.io.File;
import javax.imageio.ImageIO;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class HeadlessRenderApplication implements ApplicationRunner {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                HeadlessRenderApplication.class);
        app.setHeadless(true);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            // Runner da hoan thanh khi run(...) tra ve.
        }
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        BufferedImage image = new BufferedImage(
                320, 120, BufferedImage.TYPE_INT_ARGB);

        Graphics2D graphics = image.createGraphics();
        try {
            graphics.setColor(Color.WHITE);
            graphics.fillRect(0, 0, 320, 120);
            graphics.setColor(Color.BLUE);
            graphics.fillRect(30, 35, 220, 50);
        } finally {
            graphics.dispose();
        }

        boolean written = ImageIO.write(
                image, "png", new File("report.png"));
        if (!written) {
            throw new IllegalStateException("PNG writer unavailable");
        }

        System.out.println(
                "headless=" + GraphicsEnvironment.isHeadless());
        System.out.println("generated=report.png");
    }
}
~~~

Trong dự án Gradle đã có Spring Boot plugin, chạy:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu không có cờ JVM xung đột, runtime có hỗ trợ PNG và working directory cho phép ghi, **hai dòng do chương trình tự in ra** là:

~~~text
headless=true
generated=report.png
~~~

Các log của Spring Boot có thể xuất hiện xen trước hoặc sau. Tệp **report.png** nằm trong working directory của tiến trình; ảnh có nền trắng và hình chữ nhật xanh.

**Cơ chế:**

1. **SpringApplication.setHeadless(true)** chuẩn bị cấu hình Java AWT cho môi trường không có màn hình.
2. **WebApplicationType.NONE** bỏ web runtime không cần thiết cho job này; đó là cấu hình độc lập.
3. Spring Boot gọi bean **ApplicationRunner** khi khởi động.
4. **BufferedImage** giữ mảng pixel, **Graphics2D** vẽ vào RAM, **ImageIO** ghi PNG ra đĩa. Không có JFrame hoặc dialog.
5. Khi runner xong, **app.run(args)** trả context; try-with-resources đóng context cho chương trình một lần.

Trong một web service phục vụ ảnh qua HTTP, logic vẽ ảnh có thể dùng tương tự trong service/controller, nhưng **không đóng Spring context sau mỗi request**. Headless là lựa chọn AWT, không phải cơ chế tự động kết thúc tiến trình.

**Lưu ý:** Với ảnh chứa chữ, môi trường container tối giản có thể thiếu font cần thiết; với custom JRE tạo bằng jlink có thể thiếu module **java.desktop**. Headless không bảo đảm font, thư viện native hay quyền ghi tệp đã sẵn sàng.

## 6. Khi ứng dụng thật sự cần tương tác đồ họa

Chỉ nên chọn **headless=false** khi **chính JVM** phải tạo cửa sổ trên máy chạy nó: ví dụ desktop Swing, hộp thoại chọn tệp **JFileChooser**, cửa sổ xem trước hình ảnh hoặc phần mềm quản trị chạy cục bộ.

Điều kiện cần để mở GUI:

- Hệ điều hành có desktop và display server hoặc phiên đồ họa tương thích (Windows desktop session, macOS GUI session, Linux X11/đường tương thích).
- Tiến trình có quyền kết nối tới display đó; cấu hình **DISPLAY** trên Linux phải phù hợp nếu dùng X11.
- Java runtime có module **java.desktop** và các thư viện hệ thống cần thiết.
- Không có tham số **-Djava.awt.headless=true** hoặc lời gọi AWT sớm khiến ứng dụng tiếp tục ở chế độ headless.
- Code sử dụng luồng đồ họa phù hợp, đặc biệt **Swing Event Dispatch Thread (EDT)**.

**setHeadless(false) chỉ thay đổi cách Java sử dụng AWT; nó không tạo X server hay kết nối màn hình từ container đến máy người dùng.** Một công cụ test giao diện có thể dùng virtual display như Xvfb trong môi trường được chuẩn bị riêng. Backend web bình thường không cần thiết lập đó.

### Ví dụ Spring Boot mở Swing JFrame

Ví dụ này là **một dự án Spring Boot khác với ví dụ tạo PNG**, Java 17+, có **spring-boot-starter**, chạy tại máy desktop tương tác. Tệp **src/main/java/example/DesktopApplication.java**:

~~~java
package example;

import java.awt.event.WindowAdapter;
import java.awt.event.WindowEvent;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.SwingConstants;
import javax.swing.SwingUtilities;
import javax.swing.WindowConstants;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DesktopApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                DesktopApplication.class);
        app.setHeadless(false);
        app.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = app.run(args);

        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("Spring Boot + Swing");
            frame.setDefaultCloseOperation(
                    WindowConstants.DISPOSE_ON_CLOSE);
            frame.add(new JLabel(
                    "Spring context da khoi tao",
                    SwingConstants.CENTER));
            frame.setSize(420, 180);
            frame.setLocationRelativeTo(null);

            frame.addWindowListener(new WindowAdapter() {
                @Override
                public void windowClosed(WindowEvent event) {
                    context.close();
                }
            });

            frame.setVisible(true);
        });
    }
}
~~~

Chạy trong dự án Gradle có cấu hình phù hợp:

~~~bash
./gradlew bootRun
~~~

Trên máy có desktop hoạt động và không bị cờ JVM ép **headless=true**, chương trình hiển thị một cửa sổ tiêu đề **Spring Boot + Swing** với dòng chữ **Spring context da khoi tao**. Không có stdout cố định do mã tự in; kết quả chính là cửa sổ. Khi người dùng đóng cửa sổ, listener đóng Spring context.

**Vì sao cần thiết kế này?**

- **setHeadless(false)** được gọi trước **run(...)**; GUI chỉ tạo sau khi Spring context đã khởi động.
- **WebApplicationType.NONE** phù hợp vì đây là desktop app không cần HTTP server.
- **SwingUtilities.invokeLater(...)** tạo cửa sổ trên **EDT**. Nên giữ các thao tác liên quan UI ở EDT; tác vụ nền dài cần cơ chế điều phối riêng để tránh treo giao diện.
- **DISPOSE_ON_CLOSE** giải phóng cửa sổ khi đóng; listener **windowClosed(...)** đóng ApplicationContext. Spring context và cửa sổ có hai vòng đời khác nhau, cần đồng bộ phù hợp.
- Nếu máy không có display, ứng dụng có thể lỗi trước khi mở cửa sổ. Không giải quyết bằng cách lặp lại việc đặt headless=false.

Ví dụ tập trung vào **một cửa sổ, một context**. Ứng dụng desktop nhiều cửa sổ hoặc có công việc cần lưu khi thoát phải có shutdown policy riêng.

## 7. Chọn thiết kế trong các tình huống thực tế

**Backend trả trang React/HTML.** Spring Boot phục vụ HTTP hoặc JSON; người dùng tương tác trong browser ở phía client. Giữ **headless=true**, kể cả website có đồ thị động.

**REST API trả ảnh biểu đồ.** Render vào BufferedImage hoặc dùng thư viện hỗ trợ headless rồi gửi bytes PNG. Chạy backend headless; kiểm tra font và khả năng render nếu xuất ảnh chứa chữ.

**Job báo cáo chạy mỗi đêm trong Docker/Kubernetes.** Giữ headless, không mở JFrame/JFileChooser. Đường dẫn tệp và tham số đến từ config/CLI; không dựa vào hộp thoại nhập liệu.

**Ứng dụng desktop nội bộ có nút chọn tệp.** Nếu chạy Swing/AWT trực tiếp, dùng headless=false với desktop session; có thể tận dụng Spring DI cho tầng nghiệp vụ.

**CI kiểm thử GUI.** Chạy trong hệ thống test có desktop/virtual display phù hợp. Test API và unit thông thường không cần GUI nên giữ headless.

**Dịch vụ xuất PDF có hình ảnh.** Đừng mặc định rằng sinh PDF yêu cầu GUI. Nhiều thư viện render chạy headless; cần xác minh hỗ trợ, font và thư viện hệ thống theo implementation cụ thể.

## 8. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/xử lý |
| --- | --- | --- |
| java.awt.HeadlessException khi new JFrame/JDialog | JVM đang headless, API yêu cầu màn hình | Chỉ mở GUI trên desktop; setHeadless(false) trước startup, kiểm tra -D |
| AWTError hoặc “Can't connect to X11 window server” | Đã ép headless=false nhưng thiếu display server hoặc quyền kết nối | Bổ sung hạ tầng display thích hợp hoặc bỏ phụ thuộc cửa sổ ở backend |
| isHeadless() là true dù máy có màn hình | SpringApplication mặc định headless=true hoặc JVM ép -D=true | Kiểm tra main, launch script, JVM args trước lần dùng AWT |
| isHeadless() là false nhưng JFrame vẫn không mở | Cờ JVM false không bảo đảm OS có màn hình khả dụng | Kiểm tra desktop session, DISPLAY, toolkit/native libs |
| BufferedImage làm việc nhưng chữ trong ảnh sai font | Runtime/server thiếu font phù hợp | Cài/đóng gói font, kiểm tra encoding và render trên môi trường triển khai |
| NoClassDefFoundError với lớp java.awt khi dùng custom JRE | java.desktop không được đóng gói | Bổ sung java.desktop vào runtime tùy nhu cầu |
| Swing bị treo khi nhấn nút | Tác vụ dài chạy trên EDT | Chuyển tác vụ sang worker/background thread và cập nhật UI qua EDT |
| Đổi headless property lúc runtime không tác dụng | AWT đã được khởi tạo/cached | Cấu hình từ main/VM options trước khi toolkit tạo lần đầu |
| App không mở HTTP vì dùng WebApplicationType.NONE | Đang tắt web runtime; không phải do headless | Xem lại cấu hình loại web độc lập với AWT |

Để tìm nguyên nhân nhanh, hãy theo trình tự:

1. Phân loại lỗi là **hiển thị cửa sổ**, **render ảnh vào RAM**, hay **web server**.
2. Kiểm tra **System.getProperty("java.awt.headless")**, **GraphicsEnvironment.isHeadless()**, tham số **-D** và lời gọi **setHeadless(...)** trước khi AWT khởi tạo.
3. Nếu cần GUI thật, kiểm tra display server/desktop session và quyền truy cập của đúng tiến trình JVM.
4. Nếu chỉ cần xuất ảnh, loại bỏ JFrame, JOptionPane, JFileChooser, Toolkit.getScreenSize và các API phụ thuộc màn hình.
5. Đảm bảo font, module **java.desktop**, và vòng đời luồng GUI/tài nguyên được cấu hình hợp lý.

## 9. Những nhầm lẫn cần tránh

**“Đặt spring.main.web-application-type=none là bật headless.”** Sai. Cấu hình đó điều khiển Spring web context, không trực tiếp thiết lập AWT.

**“Đặt headless=false sẽ mở giao diện.”** Sai. Phải có đoạn code tạo UI trên máy có display và môi trường desktop thực tế.

**“Ứng dụng trả PNG cho browser phải headless=false.”** Sai. Browser hiển thị ảnh, còn backend có thể render trong RAM ở chế độ headless.

**“Có thể đổi headless tùy ý sau khi Spring khởi động.”** Không an toàn. AWT có thể đã khởi tạo và cache chế độ; hãy đặt cấu hình ngay từ JVM/main.

**“JFrame lỗi tức Spring Boot không chạy được trên Linux.”** Sai. Spring Boot không cần GUI; vấn đề thường là mã đang mở cửa sổ trên môi trường không có display.

**“Có giao diện web nên backend là ứng dụng desktop.”** Sai. Web UI hiển thị trên trình duyệt; ứng dụng backend vẫn headless.

## 10. Câu hỏi tự kiểm tra

1. **Spring Boot trên Kubernetes tạo biểu đồ PNG rồi trả cho trình duyệt: headless=true hay false?** Thông thường là true; không cần cửa sổ, nhưng phải có thư viện render và font phù hợp.
2. **Dự án Swing chạy tại Windows desktop và cần mở JFileChooser: chế độ gì?** headless=false và phiên desktop thực.
3. **JVM in headless=false trong Docker nhưng JFrame vẫn lỗi: nghịch lý?** Không. Flag false không tạo display server.
4. **Ứng dụng WebFlux trả JSON có cần tắt headless?** Không.
5. **Job non-web muốn sử dụng ImageIO, WebApplicationType.NONE có bắt buộc đồng nghĩa headless?** Không. Một cái điều khiển web runtime, một cái điều khiển môi trường AWT.
6. **Nên gọi setHeadless(false) trước hay sau SpringApplication.run(...)?** Trước, và tránh để AWT/Toolkit khởi tạo trước khi cấu hình.

**Ghi nhớ:** SpringApplication mặc định **headless=true** vì đa số ứng dụng Spring Boot là dịch vụ backend. Chỉ sử dụng **headless=false** khi chính JVM cần mở cửa sổ AWT/Swing, đồng thời bảo đảm máy thực thi có display phù hợp. **Tạo ảnh trong bộ nhớ và phục vụ website không đòi hỏi mở GUI.**

### Tài liệu tham khảo

- [Spring Boot 3.5 API — SpringApplication.setHeadless](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html)
- [Java 21 API — GraphicsEnvironment.isHeadless](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/awt/GraphicsEnvironment.html)
- [Oracle — Using Headless Mode in the Java SE Platform](https://www.oracle.com/technical-resources/articles/javase/headless.html)
