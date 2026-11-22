# Các package javax của Java SE không thuộc phạm vi đổi tên hàng loạt

Khi nâng cấp ứng dụng từ Java EE sang Jakarta EE, một quy tắc đơn giản nhưng **sai** thường được đề xuất: “thay tất cả `javax.` bằng `jakarta.`”. Thực tế, nhiều API enterprise đã chuyển namespace, nhưng những package `javax` thuộc **Java SE** vẫn giữ nguyên tên trên các JDK hiện đại. Trong cùng một ứng dụng Jakarta EE, hoàn toàn bình thường khi mã nguồn vừa import `jakarta.persistence.Entity` vừa import `javax.sql.DataSource`.

Điểm mấu chốt của **Java Advance Compatibility Migration** không phải là loại bỏ hết từ khóa `javax`, mà là xác định **API thuộc nền tảng nào, được cung cấp bởi module hoặc artifact nào và có thuộc phạm vi chuyển namespace hay không**. Nếu đổi nhầm `javax.net.ssl.SSLContext` thành `jakarta.net.ssl.SSLContext` hoặc `javax.xml.parsers.DocumentBuilderFactory` thành `jakarta.xml.parsers.DocumentBuilderFactory`, code sẽ không tìm thấy API Java SE tương ứng. Ngược lại, giữ `javax.servlet` cũ khi server đã chuyển sang Jakarta Servlet thế hệ mới có thể khiến runtime không nhận diện filter, servlet hoặc extension.

Bài này làm rõ ranh giới Java SE và Jakarta EE, các nhóm package có tên giống nhau nhưng thuộc hệ khác nhau, lỗi thường gặp khi tìm-thay hàng loạt, và quy trình chuyển đổi có kiểm chứng.

## 1. Vì sao `javax` xuất hiện ở cả Java SE lẫn Java EE?

Về lịch sử, một số API chuẩn được đưa vào nền tảng Java với namespace `javax`. Chúng bao gồm những công nghệ Java SE như JDBC DataSource, JSSE/TLS, Swing, XML parsing, JNDI và Java Management Extensions. Trong khi đó, các đặc tả enterprise như Servlet, JPA, JAX-RS, JMS và nhiều API khác cũng dùng namespace `javax` trong Java EE.

Khi Java EE chuyển sang Jakarta EE, quá trình thay đổi namespace áp dụng cho những API enterprise thuộc phạm vi Jakarta, **không áp dụng cho toàn bộ Java SE**. Jakarta EE 8 vẫn còn dùng namespace `javax` cho các API kế thừa; bước chuyển đổi chính sang `jakarta` diễn ra ở Jakarta EE 9.

Do đó, câu hỏi đúng không phải:

> “Import có bắt đầu bằng javax không?”

Mà là:

> “Class này thuộc đặc tả Java SE hay một API enterprise thuộc phạm vi đổi namespace của Jakarta EE?”

### 1.1. Ba tầng phải phân biệt

| Tầng | Chức năng | Ví dụ |
|---|---|---|
| Java SE / JDK | API nền tảng, JVM, module tiêu chuẩn | `javax.sql`, `javax.net.ssl`, `javax.xml.parsers` |
| Jakarta EE specifications | Các hợp đồng enterprise | `jakarta.servlet`, `jakarta.persistence`, `jakarta.ws.rs` |
| Implementation/framework/container | Cung cấp runtime thực thi các hợp đồng enterprise | Servlet container, JPA provider, Jakarta REST implementation |

Thay namespace enterprise không tự thay implementation tương ứng và cũng không đổi các class Java SE.

## 2. Bảng nhận diện những package javax thuộc Java SE

Các package trong bảng dưới đây là những ví dụ quan trọng **không được tự đổi sang jakarta**. Module JPMS cho biết một nguồn cung cấp API trên những JDK hiện đại; cần đối chiếu đúng JDK mục tiêu nếu dự án có cấu hình đặc biệt.

| Nhóm API Java SE | Package / class tiêu biểu | Module JPMS | Quyết định |
|---|---|---|---|
| JDBC DataSource | `javax.sql.DataSource`, `javax.sql.XADataSource` | `java.sql` | Giữ nguyên |
| JDBC RowSet | `javax.sql.rowset.CachedRowSet` | `java.sql.rowset` | Giữ nguyên |
| XA resource interface | `javax.transaction.xa.XAResource`, `Xid` | `java.transaction.xa` | Giữ nguyên |
| TLS / JSSE | `javax.net.ssl.SSLContext`, `SSLSocket` | `java.base` | Giữ nguyên |
| Mật mã | `javax.crypto.Cipher`, `SecretKey` | `java.base` | Giữ nguyên |
| Java authentication | `javax.security.auth.Subject` | `java.base` | Giữ nguyên |
| JNDI | `javax.naming.InitialContext` | `java.naming` | Giữ nguyên |
| JMX | `javax.management.MBeanServer` | `java.management` | Giữ nguyên |
| XML parser | `javax.xml.parsers.DocumentBuilderFactory` | `java.xml` | Giữ nguyên |
| XML transformation | `javax.xml.transform.TransformerFactory` | `java.xml` | Giữ nguyên |
| XML validation / XPath | `javax.xml.validation.SchemaFactory`, `javax.xml.xpath.XPathFactory` | `java.xml` | Giữ nguyên |
| Streaming XML | `javax.xml.stream.XMLInputFactory` | `java.xml` | Giữ nguyên |
| XML namespace | `javax.xml.namespace.QName` | `java.xml` | Giữ nguyên |
| XML digital signature | `javax.xml.crypto.dsig.XMLSignature` | `java.xml.crypto` | Giữ nguyên |
| Swing/GUI | `javax.swing.JFrame`, `JPanel` | `java.desktop` | Giữ nguyên |
| Desktop facilities | `javax.imageio.ImageIO`, `javax.print` | `java.desktop` | Giữ nguyên |
| Java Sound | `javax.sound.sampled`, `javax.sound.midi` | `java.desktop` | Giữ nguyên |
| Script API | `javax.script.ScriptEngineManager` | `java.scripting` | Giữ nguyên |
| Compiler APIs | `javax.tools.JavaCompiler` | `java.compiler` | Giữ nguyên |
| Annotation processing | `javax.annotation.processing.Processor` | `java.compiler` | Giữ nguyên |
| Language model | `javax.lang.model.element.TypeElement` | `java.compiler` | Giữ nguyên |

Bảng không liệt kê mọi package `javax` có trong Java SE. Khi gặp class lạ, cần xem API specification, module descriptor hoặc artifact chứa class ấy. **Không kết luận dựa trên prefix.**

## 3. Những namespace enterprise thường phải đổi

Khi nâng lên các thế hệ Jakarta EE dùng namespace mới, nhiều mapping phổ biến là:

| API enterprise cũ | API Jakarta mới | Chức năng |
|---|---|---|
| `javax.servlet` | `jakarta.servlet` | Servlet/filter/listener |
| `javax.persistence` | `jakarta.persistence` | Persistence/JPA |
| `javax.ws.rs` | `jakarta.ws.rs` | REST/JAX-RS |
| `javax.validation` | `jakarta.validation` | Bean Validation |
| `javax.inject` | `jakarta.inject` | Dependency injection |
| `javax.enterprise` | `jakarta.enterprise` | CDI |
| `javax.ejb` | `jakarta.ejb` | Enterprise Beans |
| `javax.jms` | `jakarta.jms` | Messaging |
| `javax.websocket` | `jakarta.websocket` | WebSocket |
| `javax.mail` | `jakarta.mail` | Mail |
| `javax.json` | `jakarta.json` | JSON Processing |
| `javax.json.bind` | `jakarta.json.bind` | JSON Binding |
| `javax.xml.bind` | `jakarta.xml.bind` | JAXB/XML Binding |
| `javax.xml.ws` | `jakarta.xml.ws` | JAX-WS |
| `javax.activation` | `jakarta.activation` | Activation |
| `javax.annotation.Resource` | `jakarta.annotation.Resource` | Common Annotations |
| `javax.transaction.UserTransaction` | `jakarta.transaction.UserTransaction` | Enterprise Transactions |

Đây là **bản đồ phân loại**, không phải cam kết cứ thay import là xong. Phải nâng API artifact, implementation, extension và framework/container đồng bộ theo version được hỗ trợ. Chẳng hạn, một Servlet filter đã biên dịch cho `javax.servlet.Filter` không tự động implement `jakarta.servlet.Filter`. Hai interface có fully qualified name khác nhau và là hai type khác nhau trong JVM.

## 4. Trường hợp tiêu biểu: Jakarta Persistence vẫn dùng javax.sql.DataSource

Sau migration, entity có thể dùng:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class ProductEntity {
    @Id
    private Long id;

    private String name;

    protected ProductEntity() {}
}
~~~

Đồng thời tầng JDBC vẫn dùng các type Java SE:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ProductDao {
    private final DataSource dataSource;

    public ProductDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String findName(long id) throws SQLException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement query =
                     connection.prepareStatement(
                         "SELECT name FROM product WHERE id = ?")) {
            query.setLong(1, id);

            try (ResultSet result = query.executeQuery()) {
                return result.next()
                        ? result.getString("name")
                        : null;
            }
        }
    }
}
~~~

Các file trên chỉ minh họa. `jakarta.persistence` cần API/implementation Jakarta Persistence phù hợp; `javax.sql.DataSource` thuộc Java SE và **không** được đổi thành `jakarta.sql.DataSource`.

### 4.1. JDBC driver không phải JPA API

Việc thay ORM/JPA namespace không thay đổi contract của JDBC. `java.sql.Connection`, `java.sql.PreparedStatement`, `javax.sql.DataSource` và `javax.sql.XADataSource` vẫn có tên Java SE. Một connection pool hoặc ORM provider thế hệ Jakarta có thể tiếp tục sử dụng chúng.

Khi migration gặp lỗi database, hãy phân biệt lỗi do JPA mapping, driver, schema, transaction hay dependency, thay vì mặc định import `javax.sql` là nguyên nhân.

## 5. Ngoại lệ rất dễ bỏ sót: javax.transaction.xa

Tên `javax.transaction.xa` làm nhiều người nhầm đây là phần cần đổi thành `jakarta.transaction.xa`. Trên thực tế, nhóm **XA resource interface** được cung cấp bởi Java SE và giữ nguyên namespace.

~~~java
import javax.transaction.xa.XAResource;
import javax.transaction.xa.XAException;
import javax.transaction.xa.Xid;
~~~

Trong một ứng dụng Jakarta Transactions, các API enterprise khác có thể dùng:

~~~java
import jakarta.transaction.Transactional;
import jakarta.transaction.UserTransaction;
~~~

Hai nhóm này có thể **cùng xuất hiện hợp lệ**. Không nên dùng luật `javax.transaction.* → jakarta.transaction.*` mà không loại trừ `javax.transaction.xa`.

Một XADataSource/transaction manager có thể tương tác với `XAResource` theo interface Java SE. Nếu thay bằng một type khác có tên tương tự nhưng không cùng danh tính JVM, lời gọi hoặc ép kiểu có thể thất bại.

### 5.1. Module JPMS

Trong dự án modularized, module chứa XA API là `java.transaction.xa`. Khi cần dùng trực tiếp từ một named module, khai báo dependence tương ứng trong `module-info.java`. Không suy ra module mới tên “jakarta.transaction.xa” từ việc đổi namespace enterprise.

## 6. javax.xml không phải một khối duy nhất

`javax.xml` là nhóm dễ gây nhầm vì có cả những API XML nền tảng và các công nghệ enterprise từng đi kèm JDK cũ.

### 6.1. XML APIs của Java SE vẫn giữ tên

~~~java
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.transform.TransformerFactory;
import javax.xml.validation.SchemaFactory;
import javax.xml.xpath.XPathFactory;
import javax.xml.stream.XMLInputFactory;
import javax.xml.namespace.QName;
~~~

Ví dụ DOM parser:

~~~java
import javax.xml.parsers.DocumentBuilderFactory;

DocumentBuilderFactory factory =
        DocumentBuilderFactory.newInstance();

factory.setNamespaceAware(true);
~~~

Các API parser/transformer/validation/StAX vẫn thuộc Java SE, chủ yếu ở module `java.xml`. Việc chuyển JAXB sang Jakarta không tạo ra `jakarta.xml.parsers.DocumentBuilderFactory`.

Với XML từ nguồn không tin cậy, parser còn cần cấu hình bảo mật phù hợp để hạn chế external entity và việc truy xuất tài nguyên ngoài. Đây là vấn đề bảo mật XML, không phải lý do đổi package.

### 6.2. JAXB và JAX-WS có câu chuyện khác

API JAXB cũ:

~~~java
import javax.xml.bind.JAXBContext;
~~~

API Jakarta XML Binding thế hệ namespace mới:

~~~java
import jakarta.xml.bind.JAXBContext;
~~~

Tương tự, `javax.xml.ws` thuộc những thế hệ JAX-WS trước, còn `jakarta.xml.ws` thuộc thế hệ Jakarta XML Web Services mới.

**JEP 320** loại bỏ những module Java EE và CORBA từng được đóng gói trong JDK từ **JDK 11**. Vì vậy, khi chuyển JDK 8 sang JDK 11/17/21, một ứng dụng từng dựa vào JAXB/JAX-WS có sẵn trong JDK có thể cần dependency ngoài. Nhưng không phải mọi `javax.xml` đều đã biến mất.

Có thể tồn tại hai lựa chọn tùy lộ trình:

- Duy trì một phiên bản JAXB ngoài JDK vẫn dùng namespace `javax.xml.bind` nếu framework và hợp đồng ứng dụng cần thế hệ cũ.
- Chuyển sang `jakarta.xml.bind` cùng API/implementation và framework tương thích, rồi kiểm hợp đồng XML.

Chọn một hướng theo support matrix; không trộn API/implementation chỉ vì tên class đơn giản giống nhau.

### 6.3. XML trên wire không phải Java package

Việc đổi class Java từ `javax.xml.bind` sang `jakarta.xml.bind` không có nghĩa XML namespace URI, tên element hoặc XSD nghiệp vụ phải đổi hàng loạt. XML document là dữ liệu giao tiếp có hợp đồng riêng; phải kiểm thử fixture cũ/mới trước khi thay đổi schema.

## 7. javax.annotation.processing khác javax.annotation

Đây là bẫy phổ biến khi chuyển Common Annotations.

Annotation processor sử dụng **Java SE compiler APIs**:

~~~java
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.Processor;
import javax.annotation.processing.RoundEnvironment;
import javax.lang.model.element.TypeElement;
import javax.tools.JavaCompiler;
~~~

Những package này thuộc module `java.compiler` và không đổi sang `jakarta.annotation.processing`.

Trong khi đó, ứng dụng Jakarta EE có thể cần:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.Resource;
~~~

Một ví dụ quan trọng: `javax.annotation.processing.Generated` (Java SE) không nên bị nhầm với `javax.annotation.Generated` của các API Common Annotations cũ. Hai tên gần giống nhau nhưng nguồn và lifecycle khác nhau.

### 7.1. Generated code có thể trộn cả hai namespace một cách đúng đắn

Một JPA metamodel processor có thể dùng `javax.annotation.processing` để chạy trong javac, đồng thời sinh source import `jakarta.persistence.metamodel`. Đây là hai hợp đồng khác nhau:

- API dùng để **xây annotation processor**: Java SE.
- API trong **generated source cho JPA**: Jakarta Persistence.

Nếu generated source vẫn chứa `javax.persistence` cũ, cần nâng generator/plugin hoặc cấu hình generation, **không thay API compiler Java SE**.

## 8. JNDI, JSSE, JMX, JAAS, Crypto vẫn là Java SE

Ví dụ những import hợp lệ trong một ứng dụng Jakarta EE:

~~~java
import javax.naming.InitialContext;
import javax.sql.DataSource;
import javax.net.ssl.SSLContext;
import javax.crypto.Cipher;
import javax.security.auth.Subject;
import javax.management.MBeanServer;
~~~

Ý nghĩa:

- `javax.naming`: JNDI, module `java.naming`.
- `javax.net.ssl`: SSL/TLS, module `java.base`.
- `javax.crypto`: cryptography, module `java.base`.
- `javax.security.auth`: các API authentication Java SE.
- `javax.management`: JMX, module `java.management`.
- `javax.sql`: JDBC DataSource, module `java.sql`.

Ví dụ tra cứu DataSource qua JNDI:

~~~java
import javax.naming.InitialContext;
import javax.naming.NamingException;
import javax.sql.DataSource;

public final class DataSourceResolver {
    public DataSource resolve() throws NamingException {
        InitialContext context = new InitialContext();
        try {
            return (DataSource) context.lookup(
                    "java:comp/env/jdbc/MainDataSource");
        } finally {
            context.close();
        }
    }
}
~~~

Tên JNDI là ví dụ minh họa; đường dẫn và cơ chế cấu hình thực tế phụ thuộc server/framework. Không đổi `javax.naming` sang `jakarta.naming`.

Nếu TLS fail sau khi nâng JDK, hãy kiểm certificate, truststore, protocol và hostname; package `javax.net.ssl` không bị đổi chỉ vì Jakarta EE migration.

## 9. Java Desktop và các package javax khác

Với ứng dụng desktop, `javax.swing` vẫn thuộc Java SE:

~~~java
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.SwingUtilities;

public final class HelloDesktop {
    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("Java SE");
            frame.add(new JLabel("Hello"));
            frame.setSize(300, 120);
            frame.setDefaultCloseOperation(
                    JFrame.EXIT_ON_CLOSE);
            frame.setVisible(true);
        });
    }
}
~~~

Những API như `javax.imageio.ImageIO`, `javax.print`, `javax.sound.midi`, `javax.sound.sampled` và `javax.accessibility` cũng không tự được thay thế bằng các package Jakarta cùng tên.

Một project có cả công cụ desktop và server Jakarta EE phải xử lý từng module theo dependency và API contract của nó, không áp cùng một regex trên toàn monorepo.

## 10. Ví dụ tích hợp thực tế: Servlet Jakarta và JDBC Java SE

Trong ứng dụng Jakarta Servlet, code thường hợp lệ khi sử dụng cả hai họ type:

~~~java
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import javax.sql.DataSource;
import java.io.IOException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class StatusServlet extends HttpServlet {
    private final DataSource dataSource;

    public StatusServlet(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    protected void doGet(HttpServletRequest request,
                         HttpServletResponse response)
            throws ServletException, IOException {
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT status FROM app_status WHERE id = ?")) {
            statement.setLong(1, 1L);
            try (ResultSet result = statement.executeQuery()) {
                response.setContentType("text/plain; charset=UTF-8");
                response.getWriter().write(result.next()
                        ? result.getString("status")
                        : "unknown");
            }
        } catch (SQLException failure) {
            throw new ServletException("Database error", failure);
        }
    }
}
~~~

Đoạn này minh họa **type compatibility**, không phải servlet registration hoàn chỉnh. Trong một container thực tế, cơ chế khởi tạo/inject `DataSource` phải tuân theo framework/container được dùng; một container tiêu chuẩn không mặc nhiên biết cách cung cấp constructor argument tùy ý.

Điểm quan trọng: `jakarta.servlet.http.HttpServlet` thuộc Jakarta Servlet; `javax.sql.DataSource` và `java.sql.*` thuộc Java SE. **Có cả hai trong cùng một file không phải lỗi.**

## 11. Hệ quả nếu thay thế chuỗi trên toàn repository

Một thao tác nguy hiểm:

~~~text
Find:    javax.
Replace: jakarta.
Scope:   all files
~~~

Sẽ tạo những thay đổi không hợp lệ như:

~~~text
javax.sql.DataSource
  -> jakarta.sql.DataSource                   (sai)

javax.net.ssl.SSLContext
  -> jakarta.net.ssl.SSLContext               (sai)

javax.xml.parsers.DocumentBuilderFactory
  -> jakarta.xml.parsers.DocumentBuilderFactory (sai)

javax.transaction.xa.XAResource
  -> jakarta.transaction.xa.XAResource        (sai)

javax.annotation.processing.Processor
  -> jakarta.annotation.processing.Processor  (sai)

javax.persistence.Entity
  -> jakarta.persistence.Entity               (đúng khi stack đích dùng Jakarta Persistence)
~~~

Các thay đổi sai có thể khiến compiler báo `package ... does not exist`. Nhưng không phải lỗi nào cũng xuất hiện lúc compile: một binary plugin cũ hoặc service descriptor có thể thất bại khi runtime thực thi.

### 11.1. Đừng dùng “không còn chữ javax” làm tiêu chí thành công

Một ứng dụng Jakarta EE đã migrate vẫn có thể có nhiều import `javax` hoàn toàn hợp lệ. Tiêu chí đúng là:

> Những API enterprise **thuộc phạm vi chuyển namespace** đã được nâng đồng bộ với framework/container, còn những API Java SE `javax` vẫn giữ nguyên hợp đồng và hoạt động đúng.

Nếu dùng “0 javax imports” làm build gate, nhóm có thể bị thúc đẩy sửa mã nguồn Java SE thành những tên không tồn tại.

## 12. Đổi package ảnh hưởng đến danh tính kiểu và bytecode

Hai tên:

~~~text
javax.servlet.Servlet
jakarta.servlet.Servlet
~~~

không phải bí danh cho cùng một interface. JVM nhìn thấy hai fully qualified names riêng.

Một extension đã biên dịch để implement `javax.servlet.Filter` không tự động trở thành implementation của `jakarta.servlet.Filter` khi chỉ thay servlet container. Tương tự, class được annotate bằng `javax.persistence.Entity` không tự trở thành entity Jakarta nếu provider chỉ quét `jakarta.persistence.Entity`.

Những lỗi thường gặp:

- `ClassNotFoundException` / `NoClassDefFoundError` khi thiếu namespace mà binary yêu cầu.
- `ClassCastException` khi thử ép một object thành type thuộc namespace khác.
- `NoSuchMethodError` khi descriptor mà consumer cũ gọi không còn phù hợp.
- Annotation scanner không phát hiện entity/validator/listener.
- Framework không nhận registration hoặc provider theo SPI mới.
- Code generator sinh kiểu cũ trong khi runtime đòi kiểu mới.

Kết quả compile một module chỉ cho thấy phần source đã kiểm có thể biên dịch. Cần kiểm **runtime integration** và các consumer/plugin đã biên dịch trước đó.

## 13. Dependency và container phải cùng thế hệ

Khi chuyển namespace enterprise, chọn một tổ hợp API/implementation có hỗ trợ lẫn nhau:

| Thành phần | Cần kiểm tra |
|---|---|
| Jakarta specification API | Đúng namespace và version |
| Servlet/JPA/JAX-RS/CDI implementation | Có hỗ trợ thế hệ API được chọn không? |
| Framework/starter | Dependency và auto-configuration cùng generation |
| Application server/container | Runtime nhận API namespace mới không? |
| Build plugin | WAR packaging, enhancer, annotation processor, metamodel generation |
| Direct dependencies | Không còn sử dụng enterprise API cũ ở đường đã chuyển |
| Transitive dependencies | Có extension cũ kéo API namespace trước vào không? |
| External plugins | Đã rebuild hoặc nâng cho Jakarta interfaces chưa? |
| JDK | Minimum Java version và module API được hỗ trợ |

**Đừng xóa các Java SE module `java.sql`, `java.xml`, `java.naming` chỉ để loại bỏ chữ `javax`.** Nếu WAR deploy trong container, chọn scope API dependency phù hợp với hợp đồng của container; một `jakarta.*-api` JAR không nhất thiết chứa implementation runtime.

Không phải mọi sự hiện diện đồng thời của API `javax` và `jakarta` trên classpath đều sai. Cần xác định **những type tham gia cùng một contract runtime** có bị trộn nhầm hay không.

## 14. Ranh giới JDK upgrade và Jakarta namespace migration

Một số thay đổi thường diễn ra cùng lúc nhưng có nguyên nhân khác nhau:

| Triệu chứng | Nguyên nhân có thể | Có cần rename javax → jakarta không? |
|---|---|---|
| `javax.sql.DataSource` compile bình thường | API Java SE được cung cấp bởi JDK | Không |
| `javax.xml.bind.JAXBContext` thiếu sau JDK 11 | JDK không còn bundled JAXB theo JEP 320 | Cần chọn dependency/stack; có thể chuyển Jakarta nhưng không bắt buộc chỉ vì đổi JDK |
| `InaccessibleObjectException` | Deep reflection qua ranh giới module bị chặn | Không nhất thiết; xem JPMS/framework |
| `SSLHandshakeException` | TLS/certificate/truststore hoặc security policy | Không |
| Servlet extension không chạy trên container Jakarta mới | Type `javax.servlet` và `jakarta.servlet` không tương thích | Có, ở extension enterprise hoặc chọn bản hỗ trợ |
| JPA entity không được provider nhận | Annotation API/provider lệch generation | Có thể cần migration namespace + framework |
| `javax.transaction.xa.XAResource` compile bình thường | Interface XA thuộc Java SE | Không |
| Annotation processor không tìm thấy `jakarta.annotation.processing` | Đổi nhầm Java SE compiler API | Phải khôi phục `javax.annotation.processing` |

Điều này cho thấy không thể gộp mọi lỗi migration vào một “bước đổi tên package”.

## 15. Kiểm kê import trước khi sửa

Hãy lập danh mục **tên đầy đủ** đang dùng, bao gồm:

- Source Java/Kotlin và test source.
- Generated code và annotation processor output.
- JAR của thư viện phụ thuộc.
- XML descriptors và deployment configuration.
- Strings dùng với reflection như `Class.forName`.
- `META-INF/services` và SPI provider declarations.
- Annotation class names trong metadata hoặc config.
- Serialization/wire payload có chứa fully qualified class name.
- Plugin/agent/adapter được build độc lập.

Ví dụ tìm kiếm ứng viên với ripgrep (chỉ là lệnh tham khảo cho dự án thực tế):

~~~bash
rg -n '^import (static )?javax\.' src
rg -n 'javax\.' src
~~~

Kết quả chỉ giúp tìm **candidate**. Một comment hoặc string có `javax` không tự chứng minh code đang dùng API đó; một JAR đã biên dịch có thể chứa reference mà source search không thấy.

### 15.1. Mẫu inventory

| FQCN đang dùng | Phân loại | Hành động |
|---|---|---|
| `javax.sql.DataSource` | Java SE / JDBC | Giữ nguyên |
| `javax.net.ssl.SSLContext` | Java SE / TLS | Giữ nguyên |
| `javax.xml.parsers.DocumentBuilderFactory` | Java SE / XML | Giữ nguyên |
| `javax.transaction.xa.XAResource` | Java SE / XA | Giữ nguyên |
| `javax.annotation.processing.Processor` | Java SE / compiler | Giữ nguyên |
| `javax.servlet.http.HttpServlet` | Enterprise cũ | Chuyển khi stack đích dùng Jakarta Servlet |
| `javax.persistence.Entity` | Enterprise cũ | Chuyển khi stack đích dùng Jakarta Persistence |
| `javax.xml.bind.JAXBContext` | JAXB cũ | Chọn dependency/namespace theo lộ trình |
| `javax.annotation.Resource` | Common Annotations cũ | Chuyển khi dùng Jakarta Common Annotations |
| Unknown `javax.*` | Chưa xác minh | Đánh dấu NEEDS_VERIFICATION |

Phần “chưa xác minh” rất quan trọng; đừng đoán mapping vì tên giống nhóm khác.

## 16. Cách xác minh API nằm trong Java SE

### 16.1. Quan sát module trên JDK đích

Trên JDK hỗ trợ JPMS:

~~~bash
java --list-modules
java --describe-module java.sql
java --describe-module java.xml
java --describe-module java.transaction.xa
java --describe-module java.compiler
~~~

Các lệnh trên giúp kiểm module và các package được export ở runtime đang xét. Nếu `javax.sql` nằm trong `java.sql`, đó là tín hiệu rõ không cần một package Jakarta thay thế.

Một runtime image tối giản tạo bằng `jlink` có thể không đóng gói toàn bộ module; vì vậy phải phân biệt **full JDK** với **custom image**.

### 16.2. Compile probe đúng API trên compiler/JDK mục tiêu

~~~java
import javax.sql.DataSource;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.transaction.xa.XAResource;

public class SeApiProbe {
    DataSource dataSource;
    XAResource xaResource;

    DocumentBuilderFactory factory() {
        return DocumentBuilderFactory.newInstance();
    }
}
~~~

Ví dụ biên dịch với compiler hỗ trợ `--release`:

~~~bash
javac --release 17 SeApiProbe.java
~~~

Khi compiler và môi trường được cấu hình đúng, các kiểu Java SE tương ứng phải có thể resolve trong release đó. Điều này không chứng minh Jakarta Servlet hay JPA đã được nâng vì chúng được cung cấp bởi dependency riêng.

### 16.3. Kiểm resolved dependencies

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency servlet-api
~~~

Với Maven:

~~~bash
./mvnw dependency:tree
~~~

Đây chỉ là các lệnh minh họa quá trình điều tra; chọn đúng module/configuration và không coi output giả định là bằng chứng đã chạy. Cần xác định bản API/implementation thực tế được resolve chứ không chỉ version ghi trong build file.

## 17. Chọn phạm vi refactor thay vì thay thế toàn cục

Một mapping có kiểm soát có thể bắt đầu với những nhóm enterprise đã được xác minh:

~~~text
Enterprise migration candidates:
  javax.servlet.*      -> jakarta.servlet.*
  javax.persistence.*  -> jakarta.persistence.*
  javax.ws.rs.*        -> jakarta.ws.rs.*
  javax.validation.*   -> jakarta.validation.*
  javax.inject.*       -> jakarta.inject.*

Explicit Java SE exclusions:
  javax.sql.*
  javax.transaction.xa.*
  javax.net.*
  javax.crypto.*
  javax.security.auth.*
  javax.naming.*
  javax.management.*
  javax.xml.parsers.*
  javax.xml.transform.*
  javax.xml.validation.*
  javax.xml.stream.*
  javax.annotation.processing.*
  javax.lang.model.*
  javax.tools.*
  javax.swing.*
~~~

Danh sách này **không đầy đủ**. Ví dụ `javax.xml.bind` phải được xử lý riêng so với `javax.xml.parsers`, và `javax.transaction.xa` phải được giữ nguyên dù những API enterprise khác trong `javax.transaction` thay đổi namespace.

Một IDE-aware refactor hoặc recipe của công cụ migration có thể hữu ích, nhưng phải xem rule set và diff. Nếu công cụ tự đổi cả Java SE APIs thì cần chỉnh recipe, không cố tạo thư viện `jakarta.*` không có trong specification.

## 18. ServiceLoader, annotation scanning và generated metadata

Không phải lỗi migration nào cũng hiện thành lỗi compile. Những cơ chế runtime dùng tên class và annotation có thể tiếp tục trỏ tới namespace cũ:

- Service provider file trong `META-INF/services`.
- Framework configuration chứa fully qualified class name.
- `Class.forName("javax...")` trong reflection.
- JPA entity scan, validation scan và CDI discovery.
- Servlet filters, listeners và extension registrations.
- Annotation processor/metamodel generator.
- Bytecode proxies hoặc instrumentation được build cho API cũ.

Ví dụ, một provider implementation được viết cho SPI của namespace cũ có thể không đăng ký được cho SPI Jakarta mới. Trong khi đó, các Java SE APIs như `javax.script` và `javax.annotation.processing` vẫn giữ namespace trong những SPI Java SE tương ứng.

Cần kiểm xem **metadata đang đề cập loại API nào**, không chỉ đổi mọi tên service bắt đầu bằng `javax`.

## 19. Không nhầm migration namespace với thay đổi dữ liệu trên wire

Đổi package Java có thể làm thay đổi type identity, nhưng không có nghĩa các identifier trong giao thức/serialization phải đổi tương ứng.

Với XML và JAXB, namespace URI của dữ liệu nghiệp vụ có thể giữ nguyên dù implementation chuyển sang Jakarta XML Binding. Với JSON, contract field names và datetime format có thể độc lập với tên Java package. Tuy nhiên, nếu payload chứa Java class name thì đổi từ `javax.*` sang `jakarta.*` có thể là thay đổi hợp đồng dữ liệu.

Cần test:

1. Dữ liệu do phiên bản cũ tạo có đọc được bởi phiên bản mới không?
2. Consumer cũ có đọc được payload từ provider mới trong rolling deployment không?
3. Annotation/serializer có thay default tên field, element hoặc namespace URI không?
4. Có serialized object, cache hoặc message lưu tên class Java không?
5. Nếu cần migration dữ liệu, có đường rollback hoặc roll-forward rõ ràng không?

Không chuyển đổi XML namespace nghiệp vụ chỉ vì đổi import Java.

## 20. Kiểm chứng migration theo nhiều chiều

| Kiểm tra | Điều cần xác nhận |
|---|---|
| Source compatibility | Java SE `javax` vẫn compile; enterprise API mới resolve đúng |
| Binary compatibility | Plugin/consumer cũ có cần rebuild cho namespace Jakarta mới không |
| Dependency compatibility | API, implementation, container và extension cùng thế hệ |
| Annotation metadata | JPA, CDI, validation, servlet annotation được runtime nhận diện |
| Database | `jakarta.persistence` phối hợp với `javax.sql.DataSource`, XA và driver |
| XML/JSON | Schema, dữ liệu cũ/mới, namespace và converter hoạt động đúng |
| Security | Authn/authz, validation và TLS không bị nới lỏng |
| Runtime/JDK | Minimum Java version, module access và framework/JDK support |
| CI/build | IDE, CLI, CI cùng resolved graph và generated code |
| Rolling deployment | Các consumer cùng tồn tại không phụ thuộc contract đã đổi ngoài dự kiến |

### 20.1. Positive và negative tests

Nếu đã migrate validation, test giá trị hợp lệ **và** không hợp lệ. Nếu migrate security annotation/filters, test user được phép **và** user không được phép. Một ứng dụng chạy được trang chủ nhưng bỏ qua validation do annotation namespace sai vẫn chưa hoàn tất migration.

## 21. Kế hoạch thực hiện từng bước

### Bước 1: Chốt phiên bản nguồn và đích

Ghi rõ JDK/Jakarta EE generation, container, framework, ORM, build tool, dependency và Java baseline. Tránh mô tả chung chung “đổi sang Jakarta”.

### Bước 2: Phân loại `javax` theo API owner

Dùng import scan, dependency graph, JDK module docs và package metadata. Giữ nguyên Java SE, chỉ chuyển các API enterprise thuộc phạm vi.

### Bước 3: Nâng stack enterprise đồng bộ

Chọn Jakarta API, implementation, extension và container tương thích nhau. Đừng để consumer `javax.servlet` cũ phụ thuộc vào runtime chỉ hỗ trợ `jakarta.servlet` mà không có phương án được kiểm chứng.

### Bước 4: Sửa import và metadata có chọn lọc

Sửa source, generated code, reflection strings, service descriptors và config thuộc API enterprise mục tiêu. Không sửa `javax.sql`, `javax.net.ssl`, `javax.xml.parsers` hoặc những Java SE API khác.

### Bước 5: Biên dịch và kiểm runtime

Dùng compiler release/JDK mục tiêu và resolved dependency graph rõ ràng. Chạy startup, ORM mapping, Servlet/JAX-RS, validation, DI, JDBC/XA, XML và security tests theo ứng dụng.

### Bước 6: Thử consumer và dữ liệu lịch sử

Đối với plugin, kiểm tương thích binary/type identity. Đối với XML/JSON/cache/message, kiểm khả năng đọc dữ liệu cũ và behavior mới.

### Bước 7: Ghi bằng chứng và triển khai có kiểm soát

Lưu commit, dependency/JDK versions, test reports và hạn chế đã biết. Có phương án rollback/roll-forward nếu data contract hoặc plugin namespace đã đổi.

## 22. Các sai lầm phổ biến

**“Mọi `javax.*` đều phải đổi sang `jakarta.*`.”** Sai: Java SE còn nhiều package `javax` được hỗ trợ.

**“Jakarta EE 8 đã chuyển toàn bộ namespace.”** Bước chuyển lớn diễn ra ở Jakarta EE 9.

**“Không thể có `jakarta.persistence` và `javax.sql` trong cùng ứng dụng.”** Có thể và thường đúng.

**“`jakarta.sql.DataSource` là API JDBC mới.”** Không phải API tiêu chuẩn thay thế `javax.sql.DataSource`.

**“Mọi `javax.xml` đều đã đổi.”** Không: XML parser/transformer/StAX của Java SE vẫn là `javax.xml`.

**“Mọi `javax.transaction` đều cần đổi.”** `javax.transaction.xa` thuộc Java SE.

**“`javax.annotation.processing` chính là Jakarta Common Annotations.”** Không: đây là compiler API của Java SE.

**“Một JDK mới không còn JAXB bundled nên `javax.xml.parsers` cũng mất.”** Đây là hai nhóm khác nhau.

**“Không còn import `javax.servlet` là mọi extension đều tương thích.”** Binary plugin, generated code và runtime metadata có thể vẫn dùng namespace cũ.

**“Chỉ biên dịch được thì migration thành công.”** Cần test runtime annotation scanning, container, data contract và security.

**“Có `javax` trong code nghĩa là migration còn dang dở.”** Chỉ đúng nếu đó là enterprise API cần chuyển, không đúng cho Java SE.

## 23. Checklist khi migration

- [ ] Đã ghi rõ JDK nguồn/đích và generation Java EE/Jakarta EE.
- [ ] Đã xác định API, implementation, framework và container được hỗ trợ.
- [ ] Đã phân loại các import `javax.*` theo đặc tả và artifact/module.
- [ ] Đã giữ nguyên `javax.sql`, `javax.net.ssl`, `javax.crypto`, `javax.naming` và `javax.management`.
- [ ] Đã giữ nguyên `javax.transaction.xa`.
- [ ] Đã tách `javax.xml.parsers` khỏi `javax.xml.bind`.
- [ ] Đã giữ nguyên `javax.annotation.processing` và `javax.lang.model`.
- [ ] Đã chuyển đúng `javax.servlet`, `javax.persistence` và những enterprise API cần thiết.
- [ ] Không dùng thay thế toàn bộ `javax.` → `jakarta.`.
- [ ] Đã kiểm source, generated code, reflection strings và service descriptors.
- [ ] Đã kiểm dependency graph và extension/plugin cũ.
- [ ] Đã xác nhận JDK module availability nếu dùng JPMS.
- [ ] Đã chạy compile, integration, annotation scan, data và negative security tests.
- [ ] Đã ghi rõ những consumer, môi trường hoặc code path chưa được xác minh.
- [ ] Đã lưu kết quả và phương án triển khai/rollback.

## Kết luận

**Đổi namespace Java EE sang Jakarta EE là thay đổi có phạm vi, không phải phép thay chuỗi toàn bộ `javax`.** Java SE vẫn dùng những package `javax` chính thức như `javax.sql`, `javax.transaction.xa`, `javax.net.ssl`, `javax.crypto`, `javax.xml.parsers` và `javax.annotation.processing`. Trong khi đó, nhiều API enterprise như `javax.servlet` và `javax.persistence` chuyển sang namespace `jakarta` khi ứng dụng nâng lên thế hệ Jakarta EE tương ứng.

Migration an toàn phải phân loại theo **nguồn gốc API**, nâng đồng bộ framework/implementation, chỉ sửa những FQCN thuộc phạm vi, rồi kiểm chứng source, binary, runtime, metadata, dữ liệu và security contracts. Đích đến không phải “không còn dòng `javax`”, mà là **một ứng dụng sử dụng đúng Java SE và Jakarta EE theo hợp đồng của từng nền tảng**.
