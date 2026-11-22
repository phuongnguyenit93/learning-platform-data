# Kiểm tra registration policy với hai bean trùng tên

> **Chủ đề:** Spring Framework JMX  
> **Nhóm kiến thức:** Thực hành  
> **Bài học:** Kiểm tra registration policy với hai bean trùng tên

## 1. Mục tiêu thực hành

Trong một \`MBeanServer\`, mỗi \`ObjectName\` chỉ có thể định danh **một registration tại một thời điểm**. Khi Spring \`MBeanExporter\` cố đăng ký bean khác vào tên đã tồn tại, chính sách \`RegistrationPolicy\` quyết định cách xử lý.

Sau bài lab này, bạn sẽ:

- Tạo hai bean JMX độc lập nhưng cố tình dùng **cùng một ObjectName**.
- Tạo một \`MBeanServer\` riêng để thí nghiệm không ảnh hưởng platform MBeans của JVM.
- Quan sát ba policy \`FAIL_ON_EXISTING\`, \`IGNORE_EXISTING\` và \`REPLACE_EXISTING\`.
- Đọc giá trị thực tế từ \`MBeanServer\` sau mỗi tình huống để xác định bean nào còn được đăng ký.
- Phân biệt lỗi đăng ký với lỗi Java object, naming strategy và metadata assembler.
- Hiểu khác biệt giữa “MBean cũ còn trong registry” với “MBean mới đã thay thế registration”.
- Viết integration test tái lập được, độc lập giữa các case và cleanup đúng vòng đời.
- Biết tại sao không nên chọn \`REPLACE_EXISTING\` chỉ để che lỗi đặt tên trùng ngoài ý muốn.

## 2. Kiến thức nền: ObjectName là khóa của registry

Giả sử hai bean Java có implementation khác nhau:

\`\`\`text
FirstCounter   -> value=10
SecondCounter  -> value=20
\`\`\`

Nhưng cả hai được gán cùng tên quản trị:

\`\`\`text
lab.registration:type=Counter,name=shared
\`\`\`

Một \`MBeanServer\` không cho phép đồng thời:

\`\`\`text
lab.registration:type=Counter,name=shared -> FirstCounter
lab.registration:type=Counter,name=shared -> SecondCounter
\`\`\`

Nó phải xử lý xung đột. API JMX thuần \`registerMBean\` thông thường sẽ ném \`InstanceAlreadyExistsException\` khi ObjectName đã tồn tại.

Spring cung cấp enum:

\`\`\`java
import org.springframework.jmx.support.RegistrationPolicy;
\`\`\`

với những lựa chọn liên quan:

| Policy | Khi ObjectName còn trống | Khi ObjectName đã có |
|---|---|---|
| \`FAIL_ON_EXISTING\` | Đăng ký bean mới | Báo lỗi, không chủ ý thay thế registration cũ |
| \`IGNORE_EXISTING\` | Đăng ký bean mới | Bỏ qua registration mới, giữ bean cũ |
| \`REPLACE_EXISTING\` | Đăng ký bean mới | Unregister MBean cũ rồi register MBean mới |

Sự khác biệt chỉ quan sát rõ khi hai lần đăng ký nhắm **cùng server và cùng ObjectName**. Hai bean ở hai MBeanServer khác nhau có thể có cùng ObjectName mà không xung đột.

## 3. Sơ đồ thí nghiệm

\`\`\`text
                          Test JVM
                             |
                   Isolated MBeanServer
                             |
           lab.registration:type=Counter,name=shared
                             ^
                             |
             +---------------+----------------+
             |                                |
      Exporter thứ nhất                 Exporter thứ hai
       bean value=10                    bean value=20
       đăng ký trước                    đăng ký sau
                                              |
                                              v
                                     RegistrationPolicy
                                      /       |       \
                                    FAIL    IGNORE   REPLACE
\`\`\`

Mục tiêu của bài lab là quan sát **giá trị được đọc qua JMX** sau mỗi case, thay vì chỉ nhìn method \`setRegistrationPolicy\` có được gọi hay không.

## 4. Chuẩn bị project

Có thể dùng Maven với Spring Framework JMX và JUnit 5. Trong một ứng dụng Spring Boot đã có starter phù hợp, một số dependency có thể đã được cung cấp theo dependency management.

Ví dụ cấu trúc project:

\`\`\`text
src/
  main/
    java/example/jmx/
      CounterMBean.java
      Counter.java
  test/
    java/example/jmx/
      RegistrationPolicyTest.java
\`\`\`

Các API sử dụng:

- \`javax.management.MBeanServer\`
- \`javax.management.MBeanServerFactory\`
- \`javax.management.ObjectName\`
- \`org.springframework.jmx.export.MBeanExporter\`
- \`org.springframework.jmx.support.RegistrationPolicy\`
- \`org.junit.jupiter.api.Test\`

Với Spring Framework 6.x hoặc tương đương, cần JDK phù hợp với phiên bản Spring được chọn; hãy dùng dependency management của project thay vì gắn bừa version không tương thích.

Bài tập không yêu cầu mở JMX remote port, không cần JConsole và không cần tài khoản quản trị hệ thống.

## 5. Tạo Standard MBean nhỏ để nhận biết bean

### 5.1. Management interface

\`\`\`java
package example.jmx;

public interface CounterMBean {
    int getValue();
    String getId();
}
\`\`\`

Đây là interface theo convention Standard MBean: implementation \`Counter\` có interface tên \`CounterMBean\`.

### 5.2. Implementation

\`\`\`java
package example.jmx;

public class Counter implements CounterMBean {

    private final String id;
    private final int value;

    public Counter(String id, int value) {
        this.id = id;
        this.value = value;
    }

    @Override
    public int getValue() {
        return value;
    }

    @Override
    public String getId() {
        return id;
    }
}
\`\`\`

Hai instance:

\`\`\`java
Counter first = new Counter("first", 10);
Counter second = new Counter("second", 20);
\`\`\`

Giá trị \`Id\` và \`Value\` giúp xác định **registration nào thực sự hiện diện** trong JMX registry.

Lưu ý: một bean Java tồn tại trong bộ nhớ không có nghĩa nó đã được đăng ký thành MBean. Chúng ta phải đọc qua \`MBeanServer.getAttribute\` mới biết client JMX quan sát được gì.

## 6. Dùng MBeanServer riêng cho mỗi test

Không nên thử \`REPLACE_EXISTING\` trực tiếp trên platform server nếu không có lý do rõ ràng. Tạo isolated server:

\`\`\`java
import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;

MBeanServer server =
    MBeanServerFactory.newMBeanServer("registration.lab");
\`\`\`

Và ObjectName cố định:

\`\`\`java
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "lab.registration:type=Counter,name=shared"
);
\`\`\`

\`newMBeanServer\` tạo một server mới không đăng ký vào danh sách discovery theo cách \`createMBeanServer\` làm. Điều quan trọng ở đây là test giữ reference trực tiếp đến server và truyền chính server ấy vào exporter.

Không dùng:

\`\`\`java
ManagementFactory.getPlatformMBeanServer()
\`\`\`

cho bài tập thử xung đột nếu test runner hoặc thành phần khác có thể đang đăng ký MBean cùng tên.

## 7. Cấu hình hai MBeanExporter dùng cùng server

Ý tưởng:

\`\`\`java
MBeanExporter firstExporter = new MBeanExporter();
firstExporter.setServer(server);
firstExporter.setBeans(Map.of(name.toString(), first));

MBeanExporter secondExporter = new MBeanExporter();
secondExporter.setServer(server);
secondExporter.setBeans(Map.of(name.toString(), second));
secondExporter.setRegistrationPolicy(policy);
\`\`\`

Ở đây:

- \`firstExporter\` sở hữu registration ban đầu.
- \`secondExporter\` cố đăng ký một bean khác dưới **cùng ObjectName**.
- \`policy\` chỉ áp dụng cho lần đăng ký của exporter thứ hai.
- Hai exporter được đưa cùng \`MBeanServer\`, nếu không việc trùng tên sẽ không tạo conflict.
- Chỉ dùng một ObjectName cho bài test để kết quả dễ hiểu.

Để các exporter thực sự chạy, chúng phải trải qua lifecycle khởi tạo của Spring. Không nên kết luận \`setBeans\` đồng nghĩa đã đăng ký MBean ngay lập tức.

## 8. Lifecycle exporter trong bài lab

Khi Spring tạo exporter theo lifecycle bình thường, nó thực hiện khởi tạo, đăng ký MBean và cleanup khi bị destroy.

Trong unit/integration test có thể sử dụng helper:

\`\`\`java
private static MBeanExporter exporter(
        MBeanServer server,
        ObjectName name,
        Object bean,
        RegistrationPolicy policy
) {
    MBeanExporter exporter = new MBeanExporter();
    exporter.setServer(server);
    exporter.setBeans(Map.of(name.toString(), bean));
    exporter.setRegistrationPolicy(policy);
    return exporter;
}
\`\`\`

Sau khi xây object cần khởi tạo đúng lifecycle, ví dụ gọi callback mà exporter hỗ trợ trong Spring version đang sử dụng:

\`\`\`java
exporter.afterPropertiesSet();
exporter.afterSingletonsInstantiated();
\`\`\`

Với những Spring version nơi exporter tự đăng ký ngay trong \`afterPropertiesSet\`, phải tránh gọi đăng ký lặp qua một callback khác. Khi tự quản lý lifecycle bên ngoài ApplicationContext, cần tuân thủ contract của phiên bản cụ thể. Cách ít phụ thuộc chi tiết lifecycle hơn là tạo exporter như Spring beans trong \`AnnotationConfigApplicationContext\` rồi để container gọi callback.

Bài lab bên dưới dùng **ApplicationContext tách biệt** để kiểm thử đúng hành vi của Spring mà không phải gọi nội bộ lifecycle bằng tay.

## 9. Thiết kế fixture: dùng một context cho mỗi exporter

Giả sử factory method tạo context riêng, nhưng cả hai context cùng nhận một server đã tạo ngoài:

\`\`\`text
Context #1:
  Counter(first, 10)
  MBeanExporter #1
        |
        v
  Shared isolated MBeanServer

Context #2:
  Counter(second, 20)
  MBeanExporter #2
  RegistrationPolicy selected
        |
        v
  Same isolated MBeanServer
\`\`\`

Các context được đóng ở cuối test theo thứ tự hợp lý. Điểm quan trọng là **hai exporter đều thật sự được Spring quản lý**.

Một hàm tiện ích có thể khai báo bean trực tiếp bằng \`GenericApplicationContext\`, nhưng phải chú ý việc MBeanExporter thực hiện registration vào thời điểm context refresh, và transaction/lifecycle không cần thiết cho bài lab.

## 10. Kịch bản FAIL_ON_EXISTING

Bắt đầu với server trống:

\`\`\`text
server.isRegistered(name) = false
\`\`\`

Exporter #1 đăng ký \`Counter("first", 10)\`:

\`\`\`text
server.isRegistered(name) = true
Id    = first
Value = 10
\`\`\`

Exporter #2 có:

\`\`\`java
RegistrationPolicy.FAIL_ON_EXISTING
\`\`\`

và cố đăng ký \`Counter("second", 20)\` cùng ObjectName.

Kết quả mong đợi:

- Exporter thứ hai báo lỗi xung đột khi registration.
- MBean ban đầu vẫn đang được đăng ký, trừ khi ứng dụng/test có lifecycle cleanup khác tác động.
- \`getAttribute(name, "Id")\` trả \`"first"\`.
- \`getAttribute(name, "Value")\` trả \`10\`.

Không nên kiểm tra chính xác nội dung toàn bộ exception message; thông báo có thể thay đổi theo phiên bản Spring/JDK.

## 11. Kịch bản IGNORE_EXISTING

Khởi đầu giống trên:

\`\`\`text
server: shared -> first/10
\`\`\`

Exporter thứ hai cấu hình:

\`\`\`java
RegistrationPolicy.IGNORE_EXISTING
\`\`\`

Khi gặp ObjectName đang tồn tại, Spring bỏ qua registration mới thay vì thay thế cái cũ.

Kết quả mong đợi:

\`\`\`text
isRegistered = true
Id           = first
Value        = 10
\`\`\`

Chú ý: exporter thứ hai khởi tạo thành công **không chứng minh MBean thứ hai đã được export**. Đây chính là điều bài thực hành cần quan sát.

Nếu một dashboard sau deploy vẫn thấy giá trị cũ, \`IGNORE_EXISTING\` có thể là nguyên nhân. Không hiểu “startup không lỗi” là đồng nghĩa version mới đã chiếm ObjectName.

## 12. Kịch bản REPLACE_EXISTING

Exporter thứ hai cấu hình:

\`\`\`java
RegistrationPolicy.REPLACE_EXISTING
\`\`\`

Khi tên đã có, Spring thực hiện xử lý thay thế registration.

\`\`\`text
Trước:
  shared -> first/10

Trong thay thế:
  unregister MBean cũ
  register MBean mới

Sau khi thành công:
  shared -> second/20
\`\`\`

Kết quả mong đợi:

\`\`\`text
isRegistered = true
Id           = second
Value        = 20
\`\`\`

**Không coi replacement là một hot swap nguyên tử.** Trong khoảng unregister/register, client có thể không tìm thấy ObjectName. Listener đã gắn vào MBean cũ cũng không mặc nhiên chuyển sang MBean mới.

Nếu exporter thứ nhất đóng sau khi bị exporter thứ hai thay thế, việc cleanup của exporter thứ nhất có thể ảnh hưởng registration hiện tại tùy cơ chế theo dõi ownership và lifecycle. Vì vậy bài test cần giữ cả hai context sống cho tới khi đã assert kết quả, rồi cleanup có kiểm soát.

## 13. Test mẫu với JUnit 5 và Spring GenericApplicationContext

Đoạn dưới đây minh họa ý tưởng tích hợp tương đối độc lập với annotation scanning: đăng ký exporter beans trong các context khác nhau, mỗi context tham chiếu tới cùng server.

\`\`\`java
package example.jmx;

import java.util.Map;

import javax.management.MBeanServer;
import javax.management.MBeanServerFactory;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.context.support.GenericApplicationContext;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

import static org.junit.jupiter.api.Assertions.*;

class RegistrationPolicyTest {

    private static final String OBJECT_NAME =
        "lab.registration:type=Counter,name=shared";

    private GenericApplicationContext createContext(
            MBeanServer server,
            Counter counter,
            RegistrationPolicy policy
    ) {
        GenericApplicationContext context =
            new GenericApplicationContext();

        context.registerBean(
            "exporter",
            MBeanExporter.class,
            () -> {
                MBeanExporter exporter = new MBeanExporter();
                exporter.setServer(server);
                exporter.setBeans(
                    Map.of(OBJECT_NAME, counter)
                );
                exporter.setRegistrationPolicy(policy);
                return exporter;
            }
        );

        context.refresh();
        return context;
    }

    private static String id(
            MBeanServer server,
            ObjectName name
    ) throws Exception {
        return (String) server.getAttribute(name, "Id");
    }

    private static int value(
            MBeanServer server,
            ObjectName name
    ) throws Exception {
        return (Integer) server.getAttribute(name, "Value");
    }

    @Test
    void failOnExistingKeepsFirstRegistration()
            throws Exception {
        MBeanServer server =
            MBeanServerFactory.newMBeanServer("registration.lab");
        ObjectName name = new ObjectName(OBJECT_NAME);

        try (GenericApplicationContext first =
                 createContext(
                     server,
                     new Counter("first", 10),
                     RegistrationPolicy.FAIL_ON_EXISTING
                 )) {

            assertEquals("first", id(server, name));

            assertThrows(
                RuntimeException.class,
                () -> {
                    try (GenericApplicationContext ignored =
                             createContext(
                                 server,
                                 new Counter("second", 20),
                                 RegistrationPolicy.FAIL_ON_EXISTING
                             )) {
                        fail("Expected duplicate registration failure");
                    }
                }
            );

            assertTrue(server.isRegistered(name));
            assertEquals("first", id(server, name));
            assertEquals(10, value(server, name));
        }
    }

    @Test
    void ignoreExistingKeepsFirstRegistration()
            throws Exception {
        MBeanServer server =
            MBeanServerFactory.newMBeanServer("registration.lab");
        ObjectName name = new ObjectName(OBJECT_NAME);

        try (GenericApplicationContext first =
                 createContext(
                     server,
                     new Counter("first", 10),
                     RegistrationPolicy.FAIL_ON_EXISTING
                 );
             GenericApplicationContext second =
                 createContext(
                     server,
                     new Counter("second", 20),
                     RegistrationPolicy.IGNORE_EXISTING
                 )) {

            assertEquals("first", id(server, name));
            assertEquals(10, value(server, name));
        }
    }

    @Test
    void replaceExistingPublishesSecondRegistration()
            throws Exception {
        MBeanServer server =
            MBeanServerFactory.newMBeanServer("registration.lab");
        ObjectName name = new ObjectName(OBJECT_NAME);

        GenericApplicationContext first = createContext(
            server,
            new Counter("first", 10),
            RegistrationPolicy.FAIL_ON_EXISTING
        );

        GenericApplicationContext second = null;

        try {
            second = createContext(
                server,
                new Counter("second", 20),
                RegistrationPolicy.REPLACE_EXISTING
            );

            assertTrue(server.isRegistered(name));
            assertEquals("second", id(server, name));
            assertEquals(20, value(server, name));
        } finally {
            // Context thứ hai đang quản lý registration mới.
            if (second != null) {
                second.close();
            }
            first.close();
        }
    }
}
\`\`\`

Các class \`Counter\` và \`CounterMBean\` là fixture đã khai báo ở trên. Mẫu dùng \`GenericApplicationContext.registerBean\` (có ở các dòng Spring hiện đại). Nếu project dùng Spring Framework cũ không hỗ trợ overload này, chuyển sang Java configuration tương đương.

### Ghi chú về assertion exception

Trường hợp duplicate registration có thể được Spring bọc trong \`BeanCreationException\`, \`MBeanExportException\` hoặc exception có cause là \`InstanceAlreadyExistsException\`. Do đó ví dụ test dùng \`RuntimeException\` để minh họa và cần thu hẹp loại exception theo phiên bản thư viện thực tế khi áp dụng.

Điểm quan sát cốt lõi là MBean thứ nhất vẫn tồn tại và đọc được sau lần đăng ký thất bại.

## 14. Bảng kết quả mong đợi

| Case | Exporter #2 | Có lỗi startup? | \`Id\` sau lần đăng ký thứ hai | \`Value\` |
|---|---|---|---|---|
| Control | Chưa tạo | Không | \`first\` | \`10\` |
| \`FAIL_ON_EXISTING\` | Có | Có, lỗi xung đột | \`first\` | \`10\` |
| \`IGNORE_EXISTING\` | Có | Thông thường không | \`first\` | \`10\` |
| \`REPLACE_EXISTING\` | Có | Không nếu replacement thành công | \`second\` | \`20\` |

Bảng giả định chỉ có hai exporter trong một MBeanServer riêng, registration đầu tiên thành công và không có thao tác lifecycle khác diễn ra giữa các phép đọc.

## 15. Kiểm chứng bằng MBeanInfo

Đọc metadata:

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.println(
        attr.getName() +
        " type=" + attr.getType() +
        " readable=" + attr.isReadable()
    );
}
\`\`\`

Trong fixture, cả bean thứ nhất và thứ hai cùng implementation class nên metadata gần như giống nhau. Vì vậy chỉ đọc \`MBeanInfo\` không đủ phân biệt registration nào đang active; cần đọc \`Id\` và \`Value\` như bài test.

Với các implementation khác nhau, \`MBeanInfo\` cũng giúp xác nhận contract được thay thế có thể khác, nhưng đó là một bài toán compatibility riêng.

## 16. Kiểm thử bằng JMX API thuần để so sánh

Nếu bỏ Spring exporter và gọi trực tiếp:

\`\`\`java
server.registerMBean(
    new Counter("first", 10),
    name
);

server.registerMBean(
    new Counter("second", 20),
    name
);
\`\`\`

Lần đăng ký thứ hai sẽ ném \`InstanceAlreadyExistsException\`.

JMX thuần không có tham số \`RegistrationPolicy\` cho \`registerMBean\`. Chính sách IGNORE/REPLACE là hành vi mà Spring exporter bổ sung khi xử lý exception registration.

Điều này phân biệt trách nhiệm:

\`\`\`text
JMX MBeanServer:
  bảo vệ uniqueness của ObjectName

Spring MBeanExporter:
  quyết định xử lý duplicate registration
  theo RegistrationPolicy
\`\`\`

## 17. Kiểm tra hai bean có cùng tên nhưng ở hai server khác nhau

Thử:

\`\`\`java
MBeanServer serverA =
    MBeanServerFactory.newMBeanServer("lab.a");

MBeanServer serverB =
    MBeanServerFactory.newMBeanServer("lab.b");
\`\`\`

Đăng ký cùng ObjectName vào mỗi server:

\`\`\`java
serverA.registerMBean(new Counter("first", 10), name);
serverB.registerMBean(new Counter("second", 20), name);
\`\`\`

Kết quả hợp lệ:

\`\`\`text
serverA getAttribute(Id) = first
serverB getAttribute(Id) = second
\`\`\`

Vì uniqueness chỉ áp dụng **bên trong mỗi MBeanServer**, không áp dụng toàn bộ JVM.

Nếu bạn thấy hai MBean “cùng tên” mà không có lỗi, cần xác định liệu chúng thực sự nằm trên hai server khác nhau hay chỉ có thêm key properties tạo ObjectName khác.

## 18. Phân biệt cùng ObjectName với tên gần giống

Các ObjectName sau **khác nhau**:

\`\`\`text
lab.registration:type=Counter,name=first
lab.registration:type=Counter,name=second
\`\`\`

Còn:

\`\`\`text
lab.registration:name=shared,type=Counter
lab.registration:type=Counter,name=shared
\`\`\`

là hai cách viết cùng tập key properties, được chuẩn hóa bằng \`getCanonicalName()\`.

\`\`\`java
ObjectName a = new ObjectName(
    "lab.registration:type=Counter,name=shared"
);

ObjectName b = new ObjectName(
    "lab.registration:name=shared,type=Counter"
);

System.out.println(a.equals(b)); // true
\`\`\`

Do đó, đừng căn cứ vào thứ tự key properties trong chuỗi để kết luận hai tên khác nhau. Dùng \`ObjectName.equals\` hoặc canonical name.

## 19. Chẩn đoán khi case IGNORE không như kỳ vọng

Nếu \`IGNORE_EXISTING\` mà đọc được \`second/20\`, có thể xảy ra:

1. Exporter thứ nhất chưa thực sự đăng ký.
2. Hai exporter dùng hai MBeanServer khác nhau và bạn đọc server thứ hai.
3. ObjectName không thực sự giống nhau.
4. Chính sách không được áp dụng cho exporter đang chạy.
5. Một exporter khác đã thay thế registration trước khi assert.
6. Context lifecycle khiến registration cũ bị cleanup.

Hãy kiểm tra:

\`\`\`java
assertTrue(server.isRegistered(name));
System.out.println(name.getCanonicalName());
System.out.println(server.getAttribute(name, "Id"));
\`\`\`

Và rà soát cấu hình thật của \`setServer\`, \`setBeans\`, \`setRegistrationPolicy\`, cùng thứ tự refresh context.

## 20. Chẩn đoán khi case REPLACE không như kỳ vọng

Nếu \`REPLACE_EXISTING\` không hiển thị \`second/20\`, có thể là:

- Exporter thứ hai không chạy registration.
- Bean thứ hai không đáp ứng quy tắc export.
- Replacement thất bại do exception khác.
- Không cùng ObjectName hoặc không cùng MBeanServer.
- Lệnh cleanup từ một context đã unregister tên sau khi replacement.
- Một exporter thứ ba đăng ký lại MBean khác.

Đừng cố sửa bằng cách liên tục gọi \`registerMBean\` hoặc đổi policy. Hãy thu thập exception và đối chiếu registry tại từng mốc.

## 21. Trường hợp nhiều bean trong cùng một exporter

Bài lab sử dụng **hai exporter** để chủ động tạo xung đột trên cùng server. Nếu cấu hình:

\`\`\`java
exporter.setBeans(Map.of(
    "lab.registration:type=Counter,name=shared", first,
    "lab.registration:type=Counter,name=shared", second
));
\`\`\`

thì Java \`Map.of\` sẽ ném lỗi duplicate key trước khi exporter được gọi. Đây **không phải bài test RegistrationPolicy**.

Nếu một \`Map\` cho phép ghi lại cùng key thì giá trị thứ hai có thể overwrite giá trị đầu ngay trong Java map, cũng không tạo hai registration độc lập.

Vì vậy cách đúng là tạo hai registration attempts tuần tự, ví dụ qua hai exporter hoặc một registration trực tiếp vào server trước khi exporter mới khởi tạo.

## 22. Thử với bean đã đăng ký bằng JMX thuần

Một biến thể ngắn:

1. Tạo server riêng.
2. Đăng ký \`first\` bằng \`server.registerMBean(first, name)\`.
3. Tạo \`MBeanExporter\` cho \`second\` cùng ObjectName.
4. Áp dụng từng policy và quan sát.

Ưu điểm: không phụ thuộc lifecycle của exporter thứ nhất. Nhược điểm: chỉ kiểm chứng Spring xử lý xung đột với một MBean có sẵn, không kiểm chứng tương tác giữa hai exporter/context.

Dùng biến thể này khi muốn test riêng hành vi policy, sau đó thử bài lab hai exporter để hiểu lifecycle.

## 23. Lifecycle cleanup và ownership

Một trong những điểm quan trọng của \`REPLACE_EXISTING\`: khi exporter thứ hai thay registration của exporter thứ nhất, nó không biến exporter thứ nhất thành chủ sở hữu mới của MBean thứ hai.

Có thể phát sinh tình huống:

\`\`\`text
Context A registers first/10
Context B replaces with second/20
Context A closes
Context B still active
\`\`\`

Tùy cách Spring exporter theo dõi ObjectName đã đăng ký, việc đóng context A có thể ảnh hưởng MBean đang nằm dưới tên đó. Do vậy không nên chạy thử những lifecycle phức tạp này trên một server production dùng chung mà không nắm ownership.

Trong test:

- Assert kết quả **khi cả hai context còn sống**.
- Đóng context B trước rồi mới đóng context A ở case replace.
- Không giả định MBean first sẽ tự được restore sau khi B đóng.
- Cleanup server test riêng nếu cần.
- Nếu có notification listener gắn vào MBean cũ, không mặc định listener chuyển sang MBean mới.

## 24. Tại sao FAIL_ON_EXISTING thường hữu ích?

Một xung đột ObjectName không phải lúc nào cũng là tình huống nên bỏ qua hoặc thay thế. Nó có thể báo:

- Một bean được export hai lần.
- Hai ApplicationContext cùng quản lý cùng logical name.
- Auto-configuration và exporter thủ công bị chồng.
- ObjectNamingStrategy quá rộng.
- Một service refactor dẫn tới tên trùng.
- Một monitoring MBean bị thành phần khác chiếm.

Trong các trường hợp đó, \`FAIL_ON_EXISTING\` giúp phát hiện vấn đề sớm thay vì âm thầm che lỗi.

\`IGNORE_EXISTING\` hữu ích khi thực sự muốn giữ registration trước đó, nhưng có thể khiến một deployment dùng MBean cũ.

\`REPLACE_EXISTING\` hữu ích khi chủ đích thay registration được thiết kế rõ, nhưng có nguy cơ làm mất listener, state hoặc contract cũ.

## 25. Bảng quyết định policy

| Câu hỏi | Nên cân nhắc |
|---|---|
| Trùng tên là dấu hiệu cấu hình sai? | \`FAIL_ON_EXISTING\` |
| Có một MBean đã được module khác đăng ký và muốn giữ nguyên nó? | \`IGNORE_EXISTING\`, sau khi xác nhận ownership |
| Muốn thay MBean cũ bằng phiên bản mới có chủ đích? | \`REPLACE_EXISTING\`, kèm kế hoạch compatibility |
| Không chắc MBean nào đang sở hữu tên? | Dừng và kiểm tra, không dùng REPLACE mù |
| Hai bean vốn cần tồn tại đồng thời? | Đổi ObjectName cho duy nhất, không chọn policy để giải quyết thiết kế tên sai |
| Có client đang nghe notification cũ? | Cân nhắc listener lifecycle và đăng ký lại |

Điểm cuối cùng: registration policy không thay thế thiết kế naming strategy và ownership.

## 26. Mở rộng bài thực hành: kiểm tra notification listener

Nếu MBean cũ và mới đều phát notification, có thể:

1. Đăng ký listener với MBean cũ.
2. Phát một notification để xác minh listener hoạt động.
3. Thay registration bằng \`REPLACE_EXISTING\`.
4. Phát notification từ MBean mới.
5. Quan sát listener cũ có còn nhận event không.
6. Nếu không, đăng ký lại listener và kiểm chứng.

Kịch bản này chỉ nên thực hiện với MBean fixture có hỗ trợ \`NotificationBroadcaster\` hoặc \`NotificationPublisherAware\`. Không phải Standard MBean \`Counter\` ở trên tự phát notification.

Không dùng thành công của \`isRegistered\` làm bằng chứng subscription notification đã được giữ nguyên.

## 27. Mở rộng bài thực hành: so sánh hợp đồng MBean

Thử thay \`Counter\` bằng implementation có metadata khác:

\`\`\`text
Old:
  Value : int
  Id : String

New:
  Total : long
  Source : String
\`\`\`

Nếu dùng cùng ObjectName và \`REPLACE_EXISTING\`, client cũ gọi \`getAttribute("Value")\` có thể thất bại. Tên ObjectName ổn định không bảo đảm attribute/operation compatibility.

Vì vậy khi nâng cấp MBean, cần xem:

- Attribute name, type và read/write flag.
- Operation name, signature và return type.
- Notification types.
- Client proxy/interface compatibility.
- ObjectName stability.
- State transition sau replacement.

## 28. Bài tập tự làm

### Bài A: Đổi policy

Chạy ba trường hợp và ghi bảng:

\`\`\`text
Policy:
Startup status:
isRegistered:
Id:
Value:
Exception type:
\`\`\`

### Bài B: Đổi tên bean thứ hai

Đổi ObjectName của exporter thứ hai thành:

\`\`\`text
lab.registration:type=Counter,name=other
\`\`\`

Dự đoán kết quả: không còn xung đột; hai MBean có thể cùng tồn tại nếu exporter và server được cấu hình đúng.

### Bài C: Dùng hai server khác nhau

Cho exporter #1 dùng server A, exporter #2 dùng server B, nhưng ObjectName vẫn trùng. Dự đoán: không xung đột vì mỗi server có registry riêng.

### Bài D: Đóng context A sau khi B thay thế

Quan sát registry sau khi A đóng và ghi nhận hành vi của Spring version hiện tại. Không giả định lifecycle restore. Đây là phép thử nâng cao để hiểu ownership khi hai exporter tranh cùng tên.

### Bài E: Quan sát metadata

Đọc \`MBeanInfo\` trong ba case. Giải thích vì sao metadata giống nhau không đủ phân biệt first và second nếu cả hai dùng chung class.

## 29. Câu hỏi tự kiểm tra

1. Vì sao hai bean Java khác nhau không thể cùng đăng ký một ObjectName trong một MBeanServer?
2. \`FAIL_ON_EXISTING\` làm gì khi tên đã tồn tại?
3. Vì sao \`IGNORE_EXISTING\` không đồng nghĩa bean thứ hai đã export thành công?
4. Kết quả kỳ vọng của \`REPLACE_EXISTING\` với \`first=10\` và \`second=20\` là gì?
5. Vì sao cần đọc \`getAttribute\` thay vì chỉ kiểm tra \`isRegistered\`?
6. Hai MBeanServer trong cùng JVM có chia sẻ registry không?
7. Vì sao dùng hai key giống nhau trong \`Map.of\` không kiểm thử được RegistrationPolicy?
8. Tại sao replacement không phải hot swap nguyên tử?
9. Khi context cũ đóng sau replacement, vì sao phải cân nhắc lifecycle cleanup?
10. Khi nào nên sửa ObjectName thay vì thay registration policy?

## 30. Ghi nhớ

\`\`\`text
First exporter:
  shared -> first / 10

Second exporter:
  shared -> second / 20

FAIL_ON_EXISTING:
  lỗi xung đột
  registry vẫn: first / 10

IGNORE_EXISTING:
  bỏ qua lần đăng ký thứ hai
  registry vẫn: first / 10

REPLACE_EXISTING:
  unregister first
  register second
  registry: second / 20
\`\`\`

**Nguyên tắc cốt lõi:** hãy kiểm thử \`RegistrationPolicy\` bằng **hai lần đăng ký cùng ObjectName trên cùng MBeanServer**, rồi đọc attribute để nhận biết bean nào đang thực sự được quản lý. \`FAIL_ON_EXISTING\` làm lộ xung đột, \`IGNORE_EXISTING\` giữ registration cũ, còn \`REPLACE_EXISTING\` thay registration và kéo theo rủi ro về lifecycle, state, listener và contract JMX.