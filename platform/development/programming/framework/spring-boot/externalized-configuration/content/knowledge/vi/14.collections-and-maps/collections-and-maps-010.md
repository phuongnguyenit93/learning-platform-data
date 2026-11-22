# Collection khả biến, bất biến và yêu cầu getter hoặc setter trong Spring Boot @ConfigurationProperties

## Mục tiêu

Khi cấu hình ứng dụng chỉ gồm một số nguyên hoặc một chuỗi, việc dùng Spring Boot **@ConfigurationProperties** khá trực quan: tên property được tìm thấy, giá trị được chuyển kiểu và gán vào trường Java. Với **List**, **Set** và **Map**, quá trình binding phức tạp hơn vì binder phải **tạo hoặc cập nhật cả một collection**, đôi khi còn tạo từng phần tử lồng nhau.

Một khác biệt quan trọng là hai thiết kế Java sau không hoàn toàn tương đương:

~~~java
// Getter-only, danh sách có thể thay đổi
private final List<String> hosts = new ArrayList<>();
public List<String> getHosts() { return hosts; }
~~~

~~~java
// Getter-only, danh sách không thể thay đổi
private final List<String> hosts = List.of("localhost");
public List<String> getHosts() { return hosts; }
~~~

Trong trường hợp đầu, binder kiểu JavaBean có cơ hội cập nhật collection đã có sẵn. Trong trường hợp thứ hai, đối tượng do **List.of(...)** tạo ra không hỗ trợ những thao tác thay đổi như add, clear hoặc set. Không thể suy ra “cứ có getter là Spring sẽ bind được” chỉ vì cả hai đều trả về **List<String>**.

Bài học sẽ làm rõ:

- Collection **mutable** và **immutable** khác nhau ở đâu, nhất là với getter-only properties.
- Trường hợp JavaBean binding cần setter và trường hợp một getter của collection đã khởi tạo có thể đủ.
- Vì sao **record + constructor binding** là hướng đi tự nhiên nếu muốn cấu hình có trạng thái bất biến.
- Cách biểu diễn **List**, **Set**, **Map** và phần tử dạng object trong YAML, .properties và biến môi trường.
- Sự khác nhau giữa **binding một collection** và **ghi đè collection từ nhiều PropertySource**.
- Cách xử lý mặc định, collection rỗng, validation và lỗi binding.
- Cách kiểm thử các thiết kế mutable/immutable để tránh cấu hình chạy khác mong đợi.

Ngữ cảnh là cơ chế **Spring Boot externalized configuration**, với các ví dụ Java theo phong cách Spring Boot 3.x. Khi dùng dự án có phiên bản khác, đặc biệt với constructor binding, cần áp dụng đúng API của phiên bản đang chạy.

## 1. Collection trong configuration là gì?

Một collection có thể dùng để mô tả:

- Danh sách endpoint sẽ được thử theo thứ tự.
- Danh sách miền CORS được phép.
- Các kênh thông báo hoặc tập feature đã bật.
- Map định tuyến theo tên region/tenant.
- Danh sách worker, mỗi worker có nhiều trường.
- Map các thông số theo loại giao dịch.

Ví dụ YAML:

~~~yaml
app:
  gateway:
    hosts:
      - api-a.example.test
      - api-b.example.test
    allowed-methods:
      - GET
      - POST
    labels:
      owner: platform
      region: asia
~~~

Ta có ba loại:

| Đường dẫn cấu hình | Kiểu Java dự kiến | Ý nghĩa |
| --- | --- | --- |
| app.gateway.hosts | List<String> | Danh sách theo thứ tự |
| app.gateway.allowed-methods | Set<String> hoặc List<String> | Tập các phương thức |
| app.gateway.labels | Map<String, String> | Bảng tra cứu theo key |

Cùng một YAML có thể được bind bằng JavaBean có getter/setter hoặc constructor-bound record. Tuy nhiên, yêu cầu về collection đã khởi tạo và khả năng thay đổi sẽ khác nhau giữa hai mô hình này.

### 1.1. Mutable không có nghĩa nội dung tự thay đổi lúc runtime

**Mutable collection** cho phép code gọi các phương thức thay đổi trạng thái như add, remove, put. Nó không có nghĩa Spring Boot sẽ tự đồng bộ lại collection khi một biến môi trường bị sửa sau lúc ứng dụng khởi động.

**Immutable collection** không cho phép thay đổi thông qua API của collection. Nó có thể được tạo từ dữ liệu binder ở startup, rồi được service dùng ở trạng thái chỉ đọc. Đây là hai đặc điểm độc lập:

~~~text
Mutable / Immutable
    -> Đối tượng Java có thể thay đổi trạng thái hay không?

Startup binding / Dynamic refresh
    -> Ứng dụng có cơ chế nạp lại cấu hình lúc chạy hay không?
~~~

Không nên trộn lẫn hai khái niệm.

## 2. JavaBean binding và constructor binding

Trong Spring Boot, hai hướng phổ biến để bind **@ConfigurationProperties** là:

**JavaBean binding:** binder tạo một object, dùng setter cho property thông thường, và trong một số tình huống có thể truy cập collection đã được tạo sẵn qua getter để điền nội dung.

**Constructor binding:** binder thu thập và chuyển các giá trị, sau đó tạo object bằng constructor. Với record hoặc class chỉ có các trường final, đây thường là con đường phù hợp để xây dựng cấu hình bất biến.

Sơ đồ:

~~~text
Config Data / Environment
            |
            v
    Configuration Binder
            |
            +-- JavaBean binding
            |      new Properties()
            |      setServers(...), setLabels(...)
            |      hoặc mutate collection đã khởi tạo
            |
            +-- Constructor binding
                   bind List, Map, nested values
                   new Properties(servers, labels)
                   -> object cấu hình đã được tạo
~~~

### 2.1. Vì sao getter/setter là vấn đề riêng của JavaBean?

Một JavaBean thông thường có field, getter và setter:

~~~java
private List<String> hosts = new ArrayList<>();

public List<String> getHosts() {
    return hosts;
}

public void setHosts(List<String> hosts) {
    this.hosts = hosts;
}
~~~

Setter cho phép thay một reference collection đã có bằng collection được bind. Nếu không có setter nhưng getter trả về một collection có thể thay đổi đã được khởi tạo, binder có thể xử lý collection đó theo hỗ trợ JavaBean binding.

Ngược lại, constructor binding không cần setter: giá trị collection được truyền vào constructor như một tham số. Cách này thường tương thích hơn với một mô hình immutable.

## 3. Ví dụ JavaBean với getter và setter đầy đủ

Giả sử YAML:

~~~yaml
app:
  routing:
    hosts:
      - primary.example.test
      - backup.example.test
    labels:
      environment: production
      owner: platform
~~~

Một JavaBean:

~~~java
package example.config;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.routing")
public class RoutingProperties {

    private List<String> hosts = new ArrayList<>();
    private Map<String, String> labels = new LinkedHashMap<>();

    public List<String> getHosts() {
        return hosts;
    }

    public void setHosts(List<String> hosts) {
        this.hosts = hosts;
    }

    public Map<String, String> getLabels() {
        return labels;
    }

    public void setLabels(Map<String, String> labels) {
        this.labels = labels;
    }
}
~~~

Các đường dẫn binder đọc:

~~~text
app.routing.hosts[0]           -> primary.example.test
app.routing.hosts[1]           -> backup.example.test
app.routing.labels.environment -> production
app.routing.labels.owner       -> platform
~~~

Với một bean được đăng ký đúng cách, RoutingProperties có thể nhận danh sách hai host và map có hai entry.

**Vai trò của setter:** cho phép Spring đặt reference mới cho hosts và labels. Kiểu dữ liệu được khai báo ở field là interface **List** hoặc **Map**, không nhất thiết phải dùng ArrayList/LinkedHashMap làm kiểu public.

### 3.1. Đăng ký bean cấu hình

Một cách đăng ký:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Đặt RoutingProperties trong package được quét; hoặc dùng **@EnableConfigurationProperties(RoutingProperties.class)** trong một @Configuration.

Nếu không đăng ký bean, dù getter/setter và YAML đều đúng, Spring có thể báo không tìm thấy RoutingProperties khi service cần inject. Đó là lỗi đăng ký bean, không phải lỗi mutability.

## 4. Collection đã khởi tạo và getter-only

Trong JavaBean binding, Spring Boot có hỗ trợ trường hợp một **collection/map đã được khởi tạo, còn mutable, và được expose qua getter**, nên có thể không cần setter.

Ví dụ:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.gateway")
public class GatewayProperties {

    private final List<String> hosts = new ArrayList<>();
    private final Map<String, String> labels = new LinkedHashMap<>();

    public List<String> getHosts() {
        return hosts;
    }

    public Map<String, String> getLabels() {
        return labels;
    }
}
~~~

Ở đây:

- **hosts** được tạo bằng **new ArrayList<>()**, là một mutable List.
- **labels** được tạo bằng **new LinkedHashMap<>()**, là một mutable Map.
- Hai getter trả về **chính các object đã khởi tạo**, không phải bản sao.
- Không có setter, nên không thể thay reference của field, nhưng binder có thể làm việc với dữ liệu bên trong collection theo cơ chế được hỗ trợ.

Điểm này đặc biệt hữu ích với JavaBean muốn giữ reference ổn định cho một collection cấu hình.

### 4.1. final field không đồng nghĩa immutable collection

Ví dụ:

~~~java
private final List<String> hosts = new ArrayList<>();
~~~

Từ khóa **final** ngăn gán một List mới vào field **hosts** sau khi object được khởi tạo. Nhưng nó **không cấm** thao tác:

~~~java
hosts.add("another.example.test");
hosts.clear();
~~~

Trong khi đó:

~~~java
private final List<String> hosts = List.of("localhost");
~~~

có cả reference final lẫn collection unmodifiable. Hai thiết kế phải được phân biệt.

**Kết luận:** muốn binder cập nhật qua getter-only, chú ý **khả năng thay đổi của object collection**, không chỉ từ khóa final hoặc sự tồn tại của getter.

### 4.2. Getter cần trả về object có thể làm việc được

Một getter như:

~~~java
public List<String> getHosts() {
    return new ArrayList<>(hosts);
}
~~~

trả về một bản sao. Nếu binder chỉ thao tác với bản sao đó, field thực có thể không nhận thay đổi. Đây không phải một mẫu getter-only binding đáng tin cậy.

Tương tự:

~~~java
public List<String> getHosts() {
    return List.copyOf(hosts);
}
~~~

trả về một danh sách không thể sửa. Nếu không có setter và binder cần mutate collection, thiết kế này chặn đường cập nhật.

Để hỗ trợ getter-only JavaBean binding, getter nên expose collection đã được khởi tạo, mutable, không trả bản sao hoặc wrapper bất biến.

**Lưu ý về encapsulation:** việc expose collection mutable đồng nghĩa code khác có thể sửa dữ liệu. Nếu mục tiêu kiến trúc là chỉ đọc, nên cân nhắc constructor binding và collection immutable thay vì dùng getter-only mutable rồi cố che qua một getter trả bản sao.

## 5. Collection immutable và những trường hợp thường không bind được

Java có các factory method và wrapper tạo collection không thể thay đổi qua API:

~~~java
List.of("a", "b")
Set.of("READ", "WRITE")
Map.of("region", "asia")
List.copyOf(source)
Map.copyOf(source)
Collections.unmodifiableList(source)
~~~

Nếu JavaBean được viết:

~~~java
@ConfigurationProperties(prefix = "app.gateway")
public class GatewayProperties {

    private final List<String> hosts = List.of("fallback.example.test");

    public List<String> getHosts() {
        return hosts;
    }
}
~~~

thì binder không có setter để thay reference và collection do **List.of** tạo ra không hỗ trợ thay đổi. Khi cấu hình muốn đặt hosts, cơ chế getter-only mutable binding không thể được giả định hoạt động; ứng dụng có thể gặp lỗi binding hoặc không cập nhật như mong muốn tùy đường đi cụ thể.

### 5.1. Arrays.asList không giống ArrayList

Một ví dụ dễ nhầm:

~~~java
private final List<String> hosts =
        Arrays.asList("primary.example.test", "backup.example.test");
~~~

Danh sách từ **Arrays.asList** có kích thước cố định: có thể cho phép **set(index, value)** nhưng không cho phép thêm/bớt phần tử. Nếu binder cần clear, add hoặc thay đổi số phần tử, List này không đáp ứng đầy đủ.

Đừng dùng một collection **có vẻ thay đổi được** nhưng không hỗ trợ toàn bộ thao tác cần thiết làm đích getter-only binding.

**Mẫu rõ ràng hơn:**

~~~java
private final List<String> hosts =
        new ArrayList<>(List.of("primary.example.test"));
~~~

Nó khởi tạo mặc định, đồng thời dùng ArrayList thực sự mutable.

### 5.2. Collections.unmodifiableList chỉ tạo view

~~~java
List<String> backing = new ArrayList<>();
List<String> view = Collections.unmodifiableList(backing);
~~~

View **view** không cho phép gọi add hoặc clear. Nhưng nếu code khác còn giữ **backing**, dữ liệu bên dưới vẫn có thể bị sửa và view sẽ phản ánh thay đổi ấy.

Vì vậy **unmodifiable view** không giống **immutable snapshot** theo nghĩa dữ liệu không bị thay đổi bởi bất kỳ reference nào. Nếu muốn một bản snapshot bất biến sau binding, có thể dùng **List.copyOf(...)** sau khi đã nhận dữ liệu, với điều kiện phần tử và null phù hợp.

## 6. Khi nào setter là lựa chọn đúng?

Một JavaBean có setter phù hợp khi:

- Collection có thể được thay thế bằng giá trị từ binder.
- Không muốn phụ thuộc vào việc một collection hiện hữu phải được mutate.
- Class cần hỗ trợ JavaBean conventions của framework hoặc thư viện khác.
- Field chưa được khởi tạo từ đầu và binder cần một đường để đặt giá trị mới.
- Các loại collection hoặc cấu trúc nested phức tạp yêu cầu binder khởi tạo một object thay thế.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.gateway")
public class GatewayProperties {

    private List<String> hosts;

    public List<String> getHosts() {
        return hosts;
    }

    public void setHosts(List<String> hosts) {
        this.hosts = hosts;
    }
}
~~~

Nếu property hosts xuất hiện trong Environment và binder có thể tạo List phù hợp, setter có thể nhận reference mới.

Tuy nhiên, nếu **hosts** không được cấu hình, field có thể vẫn null. Có setter không đồng nghĩa collection luôn không rỗng hoặc khác null. Hãy xác định rõ default và validation khi thiết kế.

### 6.1. Setter có thể normalize input

Ví dụ:

~~~java
public void setHosts(List<String> hosts) {
    this.hosts = hosts == null
            ? new ArrayList<>()
            : new ArrayList<>(hosts);
}
~~~

Mẫu này giữ một bản mutable copy. Nó có thể hữu ích khi muốn tách reference nội bộ khỏi List do binder cung cấp. Nhưng nếu mục tiêu cuối cùng là bất biến, class nên có getter chỉ đọc và không expose setter cho code nghiệp vụ, hoặc chọn constructor binding.

Không nên trộn quá nhiều trách nhiệm vào setter: parsing, gọi dịch vụ bên ngoài, ghi file hay thực hiện network request khi binding đều khiến startup khó dự đoán.

### 6.2. Getter/setter trên nested object

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private final Routing routing = new Routing();

    public Routing getRouting() {
        return routing;
    }

    public static class Routing {
        private final Map<String, String> labels = new LinkedHashMap<>();

        public Map<String, String> getLabels() {
            return labels;
        }
    }
}
~~~

Vì nested Routing đã được khởi tạo, binder có thể đi vào object con qua getter và cập nhật Map mutable bên trong theo hỗ trợ JavaBean binding. Nếu **routing** là null và không có đường khởi tạo hay setter phù hợp, không thể mặc định rằng binder sẽ tạo đúng mọi tầng nested.

## 7. Constructor binding: chọn immutable model mà không cần setter

Nếu yêu cầu kiến trúc là **cấu hình không bị thay đổi sau khi khởi tạo**, dùng record/constructor binding là lựa chọn tự nhiên.

~~~java
package example.config;

import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        List<String> hosts,
        Map<String, String> labels
) {}
~~~

YAML:

~~~yaml
app:
  gateway:
    hosts:
      - primary.example.test
      - backup.example.test
    labels:
      owner: platform
      region: asia
~~~

Binder đọc List và Map từ nguồn cấu hình, sau đó gọi constructor của record. Không cần:

~~~java
setHosts(...)
setLabels(...)
~~~

và không cần getter JavaBean **getHosts()**: record cung cấp accessor **hosts()** và **labels()**.

**Điểm cần hiểu:** record có các field final, nhưng field kiểu **List** hoặc **Map** có thể vẫn tham chiếu đến một collection mutable. **Record không tự làm các phần tử collection bất biến**.

### 7.1. Record không tự biến List thành immutable

Ví dụ:

~~~java
List<String> mutable = new ArrayList<>();
mutable.add("a");
GatewayProperties p = new GatewayProperties(mutable, Map.of());
mutable.add("b");
~~~

Khi chỉ có record constructor mặc định, **p.hosts()** có thể phản ánh phần tử **b** vì nó vẫn tham chiếu đến cùng List mutable.

Vì thế, nếu muốn record giữ snapshot, cần sao chép phòng vệ.

## 8. Defensive copy trong compact constructor của record

Một thiết kế bất biến hơn:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        List<String> hosts,
        Map<String, String> labels
) {
    public GatewayProperties {
        hosts = hosts == null
                ? List.of()
                : List.copyOf(hosts);

        labels = labels == null
                ? Map.of()
                : Map.copyOf(labels);
    }
}
~~~

Đây là **compact constructor** của record. Các tham số được chuẩn hóa trước khi record gán chúng vào component tương ứng.

Lợi ích:

- Binder có thể cung cấp một collection đã được tạo trong quá trình bind.
- Record chụp một bản copy rồi expose giao diện chỉ đọc.
- Những service inject record không thể gọi **hosts().add(...)** hoặc **labels().put(...)** thành công.
- Nếu nguồn List mutable được code khác giữ, các thay đổi vào nguồn sau đó không làm snapshot List đã copy tự thay đổi.

### 8.1. CopyOf có những ràng buộc

**List.copyOf**, **Set.copyOf**, **Map.copyOf** không chấp nhận các phần tử hoặc key/value null theo quy tắc của chúng. Nếu cấu hình có phần tử null, constructor có thể ném exception.

Với List:

~~~java
List.copyOf(List.of("a", "b"));
~~~

ổn, nhưng một List có null cần được xử lý theo hợp đồng cấu hình trước khi copy.

Với Map, **Map.copyOf** cũng không giữ thứ tự iteration như một cam kết nghiệp vụ. Nếu cần thứ tự được xác định cụ thể, chọn mô hình và cách copy phù hợp thay vì dựa vào iteration order ngẫu nhiên của Map.

### 8.2. Immutable ở cấp ngoài chưa chắc deep immutable

Nếu List chứa các object mutable:

~~~java
List<MutableServer> servers;
~~~

thì **List.copyOf(servers)** làm collection không thể thêm/bớt phần tử, nhưng từng **MutableServer** vẫn có thể bị sửa thông qua reference của nó.

Muốn mô hình bất biến sâu hơn, sử dụng element type bất biến như record:

~~~java
public record Server(String name, String host, int port) {}
~~~

và tránh để component của Server tham chiếu đến dữ liệu mutable chưa được copy.

## 9. Record nested với List và Map

Một ví dụ gần thực tế hơn:

~~~java
package example.config;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.cluster")
public record ClusterProperties(
        List<Node> nodes,
        Map<String, Region> regions
) {
    public ClusterProperties {
        nodes = nodes == null ? List.of() : List.copyOf(nodes);
        regions = regions == null ? Map.of() : Map.copyOf(regions);
    }

    public record Node(
            String name,
            String host,
            int port
    ) {}

    public record Region(
            String endpoint,
            Duration timeout
    ) {}
}
~~~

YAML:

~~~yaml
app:
  cluster:
    nodes:
      - name: edge-a
        host: edge-a.example.test
        port: 8080
      - name: edge-b
        host: edge-b.example.test
        port: 8081
    regions:
      asia:
        endpoint: "https://asia.example.test"
        timeout: 3s
      europe:
        endpoint: "https://eu.example.test"
        timeout: 5s
~~~

Đường dẫn property:

~~~text
app.cluster.nodes[0].name
app.cluster.nodes[0].host
app.cluster.nodes[0].port
app.cluster.nodes[1].name
app.cluster.nodes[1].host
app.cluster.nodes[1].port

app.cluster.regions.asia.endpoint
app.cluster.regions.asia.timeout
app.cluster.regions.europe.endpoint
app.cluster.regions.europe.timeout
~~~

**Node** và **Region** là record riêng, nên chính dữ liệu con cũng theo kiểu bất biến đơn giản. Bean ClusterProperties sẽ thuận tiện để inject vào nhiều service mà không lo một service tùy tiện sửa phần tử trong List hoặc thay endpoint Map.

### 9.1. Vì sao không cần setter trên từng Node?

Binder xây dựng từng Node từ các thuộc tính như **nodes[0].host**, rồi cung cấp danh sách Node cho constructor ClusterProperties. Không có yêu cầu mỗi Node phải có setter nếu constructor binding phù hợp với version đang sử dụng.

Ở một nested JavaBean mutable, binder lại có thể cần getter/setter để tạo/cập nhật Node. Hai hướng khác nhau không nên bị trộn chỉ vì chúng cùng bind từ một YAML.

## 10. Java class immutable nhưng không dùng record

Nếu dự án cần class truyền thống, có thể dùng constructor binding với field final và getter:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.queue")
public class QueueProperties {

    private final List<String> names;

    public QueueProperties(List<String> names) {
        this.names = names == null ? List.of() : List.copyOf(names);
    }

    public List<String> getNames() {
        return names;
    }
}
~~~

Với một constructor duy nhất, Spring Boot 3 có thể suy ra constructor binding trong trường hợp được hỗ trợ. Nếu class có nhiều constructor hoặc có nhu cầu chỉ định rõ constructor bind, cần dùng annotation/đăng ký phù hợp với phiên bản Spring Boot.

Không nên gắn **@Component** vào class rồi giả định nó được tạo theo cùng constructor-binding path như một bean @ConfigurationProperties được đăng ký qua **@ConfigurationPropertiesScan** hoặc **@EnableConfigurationProperties**.

### 10.1. Phân biệt constructor binding và constructor injection

Constructor binding truyền **giá trị cấu hình** được binder giải quyết theo prefix, tên tham số và kiểu đích.

Constructor injection truyền **Spring bean dependencies** do IoC container phân giải.

Hai cơ chế đều dùng constructor Java nhưng không có cùng mục đích. Một class immutable config chỉ nhận dữ liệu như List<String> hoặc Duration thường nên dùng constructor binding; một service dùng ClusterProperties để hoạt động thì nhận bean ClusterProperties qua constructor injection.

## 11. Quy tắc getter-only cho List, Set và Map

Một bảng so sánh thực hành:

| Thiết kế JavaBean | Có setter? | Trạng thái ban đầu | Khả năng binding nên dựa vào |
| --- | --- | --- | --- |
| List field null | Có | null | Setter cho phép binder đặt List |
| List ArrayList đã tạo | Không | Mutable | Binder có thể điền qua getter trong trường hợp hỗ trợ |
| Map LinkedHashMap đã tạo | Không | Mutable | Binder có thể điền/cập nhật qua getter |
| Set LinkedHashSet đã tạo | Không | Mutable | Cần xác minh hỗ trợ binding theo kiểu Set và phép cập nhật |
| List.of(...) | Không | Unmodifiable | Không phải mẫu getter-only binding phù hợp |
| Map.of(...) | Không | Unmodifiable | Không thể mutate Map qua getter |
| List.copyOf(...) | Có | Immutable | Binder có thể cần thay reference qua setter |
| Record có List/Map | Không có setter | Constructor-bound | Giá trị được truyền vào constructor |
| Record có defensive copy | Không có setter | Snapshot immutable | Constructor nhận dữ liệu rồi copy |

Bảng trên phân biệt **hướng binding nên chọn**, không phải bảo đảm mọi binder sẽ gọi một phương thức cụ thể. Với collection nhiều cấp, collection factory lạ hoặc kiểu value phức tạp, cần kiểm chứng ở phiên bản Spring Boot thực tế.

### 11.1. Đừng nhầm getter-only với read-only business API

Getter-only mutable bean có thể hỗ trợ binder, nhưng service khác có thể gọi:

~~~java
gatewayProperties.getHosts().clear();
~~~

và thay đổi trạng thái cấu hình. Việc không có **setHosts** chỉ ngăn thay reference bằng setter, không bảo vệ các phần tử List.

Nếu yêu cầu là “service chỉ được đọc”, phương án tốt hơn là trả một cấu hình bất biến sau binding, dùng record/constructor binding hoặc một lớp chỉ đọc riêng với snapshot defensive copy.

## 12. List trong YAML và .properties

YAML:

~~~yaml
app:
  queue:
    names:
      - urgent
      - standard
      - deferred
~~~

Tương đương trong .properties:

~~~properties
app.queue.names[0]=urgent
app.queue.names[1]=standard
app.queue.names[2]=deferred
~~~

Khi List nằm trong JavaBean:

~~~java
@ConfigurationProperties(prefix = "app.queue")
public class QueueProperties {

    private List<String> names = new ArrayList<>();

    public List<String> getNames() {
        return names;
    }

    public void setNames(List<String> names) {
        this.names = names;
    }
}
~~~

Spring Boot có thể bind các phần tử theo chỉ số. Nếu List được khai báo trong record:

~~~java
@ConfigurationProperties(prefix = "app.queue")
public record QueueProperties(List<String> names) {}
~~~

binder có thể thu thập dữ liệu rồi truyền List vào constructor.

### 12.1. CSV có thể dùng trong một số nguồn

Một số cách binding List hỗ trợ giá trị dạng chuỗi phân tách dấu phẩy:

~~~properties
app.queue.names=urgent,standard,deferred
~~~

Tuy nhiên, cách biểu diễn này không phải giải pháp cho mọi List phức tạp. Với List có phần tử là object gồm host, port, timeout, việc dùng các index trong YAML/.properties thường rõ ràng hơn.

Đừng mặc định placeholder **@Value** với một danh sách YAML có thể đọc được giống hệt @ConfigurationProperties: bộ xử lý placeholder và binder có hợp đồng khác nhau.

### 12.2. List của object

YAML:

~~~yaml
app:
  workers:
    - name: indexing
      concurrency: 2
    - name: exporting
      concurrency: 4
~~~

Record:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record WorkerProperties(List<Worker> workers) {
    public record Worker(String name, int concurrency) {}
}
~~~

Đường dẫn:

~~~text
app.workers[0].name
app.workers[0].concurrency
app.workers[1].name
app.workers[1].concurrency
~~~

Đây không phải Map với key "0" và "1". Binder nhận diện index của List theo cấu trúc property path.

## 13. Set: tập giá trị không trùng

Set phù hợp khi người dùng không cần một thứ tự chỉ số có ý nghĩa nghiệp vụ và muốn biểu diễn tập giá trị không trùng theo quy tắc equality.

Ví dụ:

~~~yaml
app:
  security:
    allowed-methods:
      - GET
      - POST
      - DELETE
~~~

Record:

~~~java
import java.util.Set;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.security")
public record SecurityProperties(Set<String> allowedMethods) {}
~~~

Nếu cần thứ tự cố định cho việc hiển thị hoặc ưu tiên xử lý, hãy cân nhắc **List** thay vì Set.

### 13.1. Những giới hạn khi nói “không trùng”

Set sử dụng **equals/hashCode** của phần tử để quyết định phần tử trùng. Đối với String, **"GET"** và **"get"** là hai String khác nhau nếu chưa chuẩn hóa dữ liệu. Spring Boot không tự hiểu hai giá trị là cùng một phương thức HTTP chỉ vì ứng dụng muốn so sánh không phân biệt hoa/thường.

Một constructor có thể normalize:

~~~java
public SecurityProperties {
    if (allowedMethods == null) {
        allowedMethods = Set.of();
    } else {
        allowedMethods = Set.copyOf(allowedMethods);
    }
}
~~~

Đoạn này tạo snapshot unmodifiable, nhưng không tự chuyển mọi chuỗi thành chữ hoa. Nếu cần chuẩn hóa, hãy thiết kế bước rõ ràng và kiểm tra giá trị được phép.

### 13.2. Getter-only Set cần thận trọng

Một **HashSet** hoặc **LinkedHashSet** mutable có thể hỗ trợ các thao tác cập nhật, nhưng đừng suy luận từ ví dụ getter-only Map/List rằng mọi kiểu Set tùy biến đều được Spring Boot bind qua getter với cùng cơ chế.

Với cấu hình Set quan trọng, giải pháp dễ dự đoán là dùng **setter** trong JavaBean hoặc **constructor binding**. Kiểm tra phiên bản Spring Boot thực tế khi quyết định giữ getter-only Set.

## 14. Map: key động và collection mutable

YAML:

~~~yaml
app:
  catalog:
    regions:
      asia: "https://asia.example.test"
      europe: "https://eu.example.test"
~~~

JavaBean getter-only mutable Map:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.catalog")
public class CatalogProperties {

    private final Map<String, String> regions = new LinkedHashMap<>();

    public Map<String, String> getRegions() {
        return regions;
    }
}
~~~

Với cơ chế binder hỗ trợ mutable map, các entry **asia** và **europe** có thể được đưa vào Map đã khởi tạo. Không cần tạo field Java tên **asia** và **europe**, vì chúng là key dữ liệu động.

### 14.1. Getter-only Map.of không phù hợp

~~~java
private final Map<String, String> regions = Map.of(
        "default", "https://default.example.test"
);

public Map<String, String> getRegions() {
    return regions;
}
~~~

Map do **Map.of** tạo ra không cho phép put/remove. Nếu cần bind thêm entry hoặc thay entry, getter-only Map không đủ.

Nếu muốn giữ default mà vẫn dùng mutable JavaBean:

~~~java
private final Map<String, String> regions =
        new LinkedHashMap<>(Map.of(
                "default", "https://default.example.test"
        ));
~~~

Tuy nhiên, với nhiều PropertySource, cách Map được merge có thể ảnh hưởng entry default. Không nên tự giả định default và override sẽ luôn kết hợp theo đúng cách mong muốn nếu có nhiều nguồn ghi cùng key.

### 14.2. Map của object

~~~yaml
app:
  policies:
    fast:
      retries: 2
      backoff: 100ms
    reliable:
      retries: 5
      backoff: 1s
~~~

Record:

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record PolicyProperties(Map<String, Policy> policies) {
    public record Policy(int retries, Duration backoff) {}
}
~~~

Các path:

~~~text
app.policies.fast.retries
app.policies.fast.backoff
app.policies.reliable.retries
app.policies.reliable.backoff
~~~

Cấu trúc này phù hợp nếu key **fast** và **reliable** được xác định từ dữ liệu config. Với trường hợp có các object cố định, một nested record có field đặt tên cụ thể có thể dễ tìm lỗi hơn.

## 15. Map key đặc biệt và bracket notation

Khi key của Map chứa dấu chấm, dấu gạch chéo hoặc ký tự có ý nghĩa trong property path, không nên luôn viết như một key thông thường.

Ví dụ key **tenant.eu** phải giữ dấu chấm như một phần tên tenant:

~~~yaml
app:
  tenants:
    "[tenant.eu]":
      endpoint: "https://eu.example.test"
~~~

Trong .properties:

~~~properties
app.tenants.[tenant.eu].endpoint=https://eu.example.test
~~~

Bracket notation giúp binder hiểu rằng **tenant.eu** là một key của Map, không phải hai cấp **tenant** và **eu**.

Với key **/internal/path**:

~~~yaml
app:
  headers:
    "[/internal/path]": enabled
~~~

Điểm này là **quy tắc nhận diện key Map**, không phải hệ quả của mutable hay immutable collection. Một Map immutable vẫn phải nhận đúng key trước khi record có thể copy nó.

### 15.1. Map<String, String> và Map<String, Object>

Kiểu value của Map ảnh hưởng đến cách binder phân giải nested path và dấu chấm. Không giả định rằng mọi dấu chấm trong mọi loại Map đều tự biến thành key literal.

Nếu key động có ký tự đặc biệt, hãy sử dụng bracket notation hoặc một nguồn cấu hình bảo toàn key phù hợp, sau đó xác minh key thực tế bằng unit test.

### 15.2. Không giữ reference mutable do bên ngoài cấp

Nếu cấu hình là một Map được constructor-bound:

~~~java
public PolicyProperties {
    policies = policies == null
            ? Map.of()
            : Map.copyOf(policies);
}
~~~

thì code sử dụng không thể dễ dàng thay entry thông qua accessor. Nhưng nếu value **Policy** là một JavaBean mutable thay vì record, Map.copyOf chỉ đóng băng cấu trúc Map, không đóng băng object value.

## 16. Ghi đè List từ nhiều nguồn cấu hình

Mutability của Java collection **không quyết định quy tắc precedence** khi Spring Boot đọc nhiều nguồn.

Ví dụ application.yml:

~~~yaml
app:
  servers:
    - name: alpha
      host: alpha.example.test
    - name: beta
      host: beta.example.test
~~~

application-prod.yml:

~~~yaml
app:
  servers:
    - name: production
      host: prod.example.test
~~~

Khi profile **prod** hoạt động, Spring Boot thường bind **List** từ nguồn có độ ưu tiên cao hơn. Kết quả dự kiến là danh sách với phần tử **production**, không phải danh sách ba phần tử alpha, beta, production.

Đây là quy tắc **List replacement** khi bind nhiều PropertySource, không phải vì JavaBean có setter hay vì record immutable.

### 16.1. Vì sao không nên chỉ override một index rồi mong merge?

Giả sử file nền có:

~~~yaml
app:
  servers:
    - name: alpha
      host: alpha.example.test
    - name: beta
      host: beta.example.test
~~~

Một nguồn ưu tiên cao hơn chỉ cung cấp:

~~~properties
app.servers[0].name=production
~~~

Không nên suy đoán rằng kết quả sẽ là:

~~~text
[0] name=production, host=alpha.example.test
[1] name=beta, host=beta.example.test
~~~

Spring Boot có quy tắc chọn List từ nguồn ưu tiên cao thay vì hợp nhất tùy ý từng phần tử. Việc thiếu host ở nguồn thắng có thể tạo ra phần tử không đủ dữ liệu hoặc lỗi validation, và phần tử từ nguồn thấp hơn có thể không được giữ.

**Cách an toàn:** nếu override một List, khai báo đầy đủ danh sách mong muốn ở nguồn ưu tiên cao hơn.

### 16.2. Tự chọn immutable record không thay đổi precedence

Ngay cả khi record dùng **List.copyOf**, danh sách nào được binder đưa tới constructor vẫn tuân theo quy tắc nguồn cấu hình. Defensive copy chỉ ngăn biến đổi **sau khi object được tạo**; nó không biến List replacement thành List merge.

## 17. Ghi đè Map từ nhiều nguồn cấu hình

Map thường có cách kết hợp khác List.

application.yml:

~~~yaml
app:
  labels:
    owner: platform
    region: global
~~~

application-prod.yml:

~~~yaml
app:
  labels:
    region: asia
    tier: critical
~~~

Với cách binding Map thông thường, các key khác nhau có thể được kết hợp qua nguồn:

~~~text
owner = platform
region = asia
tier = critical
~~~

Ở key **region** trùng nhau, nguồn ưu tiên cao hơn cung cấp giá trị **asia**. Key **owner** không có ở file prod nên vẫn có thể lấy từ file nền.

Đây là **quy tắc merge của Map qua PropertySource**, không có nghĩa Map phải là mutable ở cuối cùng. Record có thể nhận Map đã được binder tổng hợp rồi **Map.copyOf** để dùng chỉ đọc.

### 17.1. Map nested value còn cần xét từng field

Với **Map<String, Region>**, một Region có thể gồm endpoint, timeout và retries. Những field này cũng tham gia binding theo tên property và các nguồn. Khi trùng key và nhiều source chỉ định các thuộc tính con khác nhau, việc kết hợp có thể phức tạp hơn Map<String, String>.

Nếu bản ghi region phải luôn đầy đủ, dùng validation và ví dụ triển khai rõ ràng. Đừng lấy ví dụ Map scalar đơn giản để bảo đảm việc merge object nested trong mọi tình huống.

## 18. Biến môi trường cho List và Map

Với **List**:

~~~text
app.servers[0].name -> APP_SERVERS_0_NAME
app.servers[0].host -> APP_SERVERS_0_HOST
app.servers[1].name -> APP_SERVERS_1_NAME
app.servers[1].host -> APP_SERVERS_1_HOST
~~~

Trong tên env, chỉ số phần tử được bao quanh bởi dấu gạch dưới.

Ví dụ lệnh:

~~~bash
APP_SERVERS_0_NAME=production APP_SERVERS_0_HOST=prod.example.test java -jar demo.jar
~~~

Với **Map** đơn giản:

~~~text
app.labels.region -> APP_LABELS_REGION
app.labels.owner  -> APP_LABELS_OWNER
~~~

Cần thận trọng nếu key của Map có chữ hoa có ý nghĩa hoặc ký tự đặc biệt. Quy tắc OS environment variable và relaxed binding có thể chuẩn hóa key khiến nó không giữ nguyên cách viết mong đợi.

Một biến môi trường có tên đúng có thể vẫn không thắng một nguồn ưu tiên cao hơn, như JVM system property hoặc command-line argument. Phải tách bạch **đổi tên**, **precedence** và **mutability của Java object**.

## 19. Default value: null, rỗng và đã khởi tạo

Có ba tình huống khác nhau:

**Không khai báo property collection:**

~~~yaml
app:
  name: demo
~~~

**Khai báo danh sách rỗng:**

~~~yaml
app:
  servers: []
~~~

**Khai báo danh sách có một phần tử:**

~~~yaml
app:
  servers:
    - name: alpha
      host: alpha.example.test
~~~

Nếu record là:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(List<Server> servers) {
    public record Server(String name, String host) {}
}
~~~

thì một property vắng mặt có thể khiến component **servers** nhận null theo chiến lược binding, còn danh sách rỗng nếu được binder nhận diện có ý nghĩa khác. Đừng tự giả định rằng vắng mặt, YAML null và [] luôn là một kết quả.

### 19.1. Default ở JavaBean

~~~java
private List<String> hosts = new ArrayList<>();
~~~

Cách này tạo một List rỗng ngay khi object được tạo. Có thể đặt vài giá trị mặc định:

~~~java
private List<String> hosts =
        new ArrayList<>(List.of("localhost"));
~~~

Nếu config runtime khai báo hosts, binder có thể thay thế hoặc cập nhật List theo cơ chế JavaBean; không nên kết luận phần tử localhost chắc chắn được giữ như phần tử đầu tiên.

### 19.2. Default trong record

~~~java
public record GatewayProperties(List<String> hosts) {
    public GatewayProperties {
        hosts = hosts == null ? List.of() : List.copyOf(hosts);
    }
}
~~~

Cách này bình thường hóa **null** ở ranh giới constructor thành List rỗng. Nó không tự định nghĩa cách YAML **servers: []** được tất cả PropertySource xử lý, nhưng bảo vệ code sử dụng khỏi trường hợp component null.

Một hướng khác là đặt default trong cấu hình nền:

~~~yaml
app:
  gateway:
    hosts:
      - localhost
~~~

Hãy xác định rõ muốn default đến từ file nền, annotation/constructor hay logic Java. Tránh để nhiều lớp default xung đột nhau.

### 19.3. @DefaultValue trong constructor binding

Spring Boot cung cấp annotation **@DefaultValue** cho các trường hợp constructor binding phù hợp. Nó có thể giúp khai báo default cho một tham số, kể cả khi cần tạo nested object tùy theo phiên bản và kiểu dữ liệu.

Ví dụ ý tưởng:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.queue")
public record QueueProperties(
        @DefaultValue("standard") List<String> names
) {}
~~~

Việc dùng @DefaultValue với collection cần bám vào khả năng chuyển đổi và cú pháp annotation trong phiên bản Spring Boot thực tế. Với danh sách mặc định phức tạp, YAML nền hoặc compact constructor có thể dễ đọc hơn.

## 20. Validation của collection và từng phần tử

Một List có thể được bind mà vẫn không hợp lệ: rỗng, trùng tên, phần tử thiếu host hoặc port không hợp lệ.

Ví dụ với Jakarta Validation:

~~~java
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record ValidatedProperties(
        @Valid @NotEmpty List<Server> servers,
        @Valid @NotNull Map<String, Region> regions
) {
    public record Server(
            @NotBlank String name,
            @NotBlank String host,
            @Min(1) int port
    ) {}

    public record Region(
            @NotBlank String endpoint
    ) {}
}
~~~

**@Validated** kích hoạt validation cho bean cấu hình khi có provider phù hợp. **@Valid** yêu cầu kiểm tra lan xuống nested element/value theo quy tắc Jakarta Validation.

**@NotEmpty** phù hợp khi một collection phải có ít nhất một phần tử. **@NotNull** chỉ yêu cầu collection tồn tại, không bắt buộc có entry.

### 20.1. Null và empty có thể khác nhau về hợp đồng

Nếu nghiệp vụ cho phép không có region nào, Map rỗng là hợp lệ. Nhưng nếu thiếu key cấu hình region là lỗi triển khai, @NotNull đơn thuần có thể không đủ để phát hiện Map rỗng. Dùng @NotEmpty khi phù hợp.

Với List, **@NotEmpty** giúp phát hiện cả null và list rỗng. Nó không bảo đảm các phần tử con hợp lệ, nên cần **@Valid** và constraints trong Server.

### 20.2. Validate sau khi tạo immutable copy

Compact constructor có thể normalize null thành List.of(). Lúc validation chạy, trường servers là một List rỗng chứ không còn null. Nếu dùng @NotEmpty, kết quả vẫn là vi phạm rõ ràng.

Tuy nhiên, nếu record constructor làm Map.copyOf khi dữ liệu chứa null, exception có thể xuất hiện ngay trong constructor trước khi thông báo Bean Validation. Vì vậy với cấu hình cần thông báo lỗi chi tiết, cần cân nhắc thứ tự normalize, kiểm tra dữ liệu và copy.

### 20.3. Tránh log collection có secret

Một Map cấu hình có thể chứa credential hoặc token. Đừng log:

~~~java
System.out.println(properties);
~~~

nếu record toString mặc định có thể chứa secret. Khi chẩn đoán binding, chỉ in tên khóa hoặc những giá trị mô phỏng không nhạy cảm.

## 21. Mutable collection và thread safety

Các collection như ArrayList và HashMap là mutable nhưng **không tự thread-safe**. Nếu một service có thể sửa config List sau khi Spring khởi động, các service khác có thể nhìn thấy trạng thái không nhất quán.

Ví dụ không nên thực hiện trong code nghiệp vụ:

~~~java
properties.getHosts().add(requestHost);
~~~

Trường hợp này vừa thay dữ liệu cấu hình toàn hệ thống, vừa có thể tạo race condition trong ứng dụng web đa luồng.

Nếu cấu hình chỉ cần đọc sau startup, nên dùng:

- Record constructor-bound và defensive copy.
- Một lớp immutable sau bước binding.
- Service chỉ nhận một interface/view chỉ đọc, khi có lý do kiến trúc phù hợp.

Nếu cần thay đổi giá trị **thực sự động**, hãy xây dựng một cơ chế trạng thái runtime riêng có đồng bộ, validation và vòng đời được định nghĩa rõ. Không biến @ConfigurationProperties mutable thành nơi lưu state của request.

## 22. @Value với collection: khác Binder của @ConfigurationProperties

Một số người thử:

~~~java
@Value("${app.queue.names}")
private List<String> names;
~~~

Cách này có thể hoạt động với một số định dạng property String, ví dụ một chuỗi danh sách phân tách dấu phẩy. Nhưng không nên giả định nó xử lý **mỗi kiểu List/Map lồng nhau trong YAML** giống binder của @ConfigurationProperties.

**@Value** chủ yếu giải quyết placeholder và chuyển kiểu ở điểm inject. **@ConfigurationProperties** cung cấp binder chuyên dụng cho cấu trúc, tên canonical, collection index, map key và nested object.

Với List<Server> hoặc Map<String, Region>, nên mô hình hóa bằng @ConfigurationProperties. Điều này cũng giúp việc validate các phần tử trở nên rõ ràng.

### 22.1. Khi chỉ có một danh sách đơn giản

Nếu ứng dụng cần một danh sách vài tag không có cấu trúc con, @Value có thể đủ trong một ví dụ nhỏ. Nhưng khi thay định dạng từ comma-separated string sang YAML list, hành vi cần được kiểm tra, không giả định binder giống nhau.

Với cấu hình vận hành dài hạn, ưu tiên API giữ được một contract rõ về tên, kiểu, default và precedence.

## 23. Nested object cũng có yêu cầu getter/setter tương tự

Một JavaBean có nested object:

~~~java
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private Http http = new Http();

    public Http getHttp() {
        return http;
    }

    public static class Http {

        private List<String> proxies = new ArrayList<>();

        public List<String> getProxies() {
            return proxies;
        }

        public void setProxies(List<String> proxies) {
            this.proxies = proxies;
        }
    }
}
~~~

Nếu **http** đã được tạo, binder có thể cập nhật các child properties của Http qua getter, không nhất thiết cần setter cho http. Nhưng cấu trúc này chỉ phù hợp khi cách tạo nested object và accessors đáp ứng binder.

Nếu nested object là immutable record nhưng outer class là JavaBean, hoặc ngược lại, cần xác định mỗi tầng được khởi tạo bằng setter hay constructor. Không trộn vô thức các pattern rồi coi binder sẽ tự suy diễn mọi constructor và getter.

### 23.1. Nested object null

Nếu:

~~~java
private Http http;
public Http getHttp() { return http; }
~~~

mà không có setter, binder có ít lựa chọn hơn để điền nested object. Khởi tạo sẵn Http mutable hoặc cung cấp setter là cách diễn đạt rõ hơn cho JavaBean binding.

### 23.2. @NestedConfigurationProperty không phải công tắc làm getter hoạt động

Annotation **@NestedConfigurationProperty** liên quan chủ yếu đến metadata cấu hình phục vụ công cụ/IDE. Nó không biến một List.of thành ArrayList, không tạo setter, không sửa một getter trả bản sao và không làm một object immutable trở nên mutable.

Đừng dùng annotation metadata để chữa lỗi getter/setter hoặc constructor binding.

## 24. Đăng ký constructor-bound bean đúng cách

Ví dụ record:

~~~java
@ConfigurationProperties(prefix = "app.cluster")
public record ClusterProperties(List<String> nodes) {
    public ClusterProperties {
        nodes = nodes == null ? List.of() : List.copyOf(nodes);
    }
}
~~~

Trong Spring Boot thông thường, đăng ký qua:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {
}
~~~

hoặc:

~~~java
@Configuration
@EnableConfigurationProperties(ClusterProperties.class)
class ClusterConfiguration {
}
~~~

Đừng viết:

~~~java
@Component
@ConfigurationProperties(prefix = "app.cluster")
public record ClusterProperties(List<String> nodes) {}
~~~

rồi mặc nhiên coi constructor duy nhất là constructor binding theo cách trên. Constructor binding cần được quản lý bởi cơ chế configuration-properties thích hợp; @Component thông thường nằm trong vòng đời tạo bean khác.

Với JavaBean có no-arg constructor và setter, đăng ký dạng component có thể có những đường đi khác, nhưng cách tổ chức đơn nhất qua scan/enable sẽ dễ hiểu hơn cho dự án.

## 25. Lỗi “UnsupportedOperationException” khi bind

Nếu ứng dụng có getter-only:

~~~java
private final List<String> hosts = List.of();

public List<String> getHosts() {
    return hosts;
}
~~~

và Binder tìm cách cập nhật List, một thao tác như add/clear có thể ném **UnsupportedOperationException**, hoặc binding không hoàn thành theo hướng cập nhật mong đợi.

Phương án sửa tùy mục tiêu:

**Muốn JavaBean mutable và getter-only:**

~~~java
private final List<String> hosts = new ArrayList<>();

public List<String> getHosts() {
    return hosts;
}
~~~

**Muốn JavaBean cho phép thay List:**

~~~java
private List<String> hosts = List.of();

public List<String> getHosts() {
    return hosts;
}

public void setHosts(List<String> hosts) {
    this.hosts = List.copyOf(hosts);
}
~~~

Cần kiểm tra phương thức setter và version binder thực tế: nếu binder thao tác mutate collection hiện hữu trước khi gọi setter, chỉ thêm setter nhưng vẫn khởi tạo immutable collection có thể không đạt kết quả kỳ vọng. Trong trường hợp này, khởi tạo bằng mutable collection cho quá trình JavaBean binding hoặc chuyển hẳn sang constructor binding thường rõ ràng hơn.

**Muốn bất biến sau startup:**

~~~java
@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(List<String> hosts) {
    public GatewayProperties {
        hosts = hosts == null ? List.of() : List.copyOf(hosts);
    }
}
~~~

Mẫu cuối giúp mô hình đích là immutable mà không cần binder mutate một List.of được tạo sẵn trong getter-only JavaBean.

## 26. Lỗi getter trả wrapper unmodifiable

Một mẫu dễ xuất hiện khi cố gắng bảo vệ encapsulation:

~~~java
private final List<String> hosts = new ArrayList<>();

public List<String> getHosts() {
    return Collections.unmodifiableList(hosts);
}
~~~

Getter công khai không cho code khác sửa List, nhưng binder JavaBean getter-only cũng chỉ thấy unmodifiable view. Nếu không có setter hoặc một cơ chế khác, cách bind trực tiếp vào collection này không thể được mặc định đảm bảo.

**Giải pháp kiến trúc:** tách giai đoạn tạo cấu hình khỏi giai đoạn cung cấp view chỉ đọc, hoặc dùng constructor binding với defensive copy. Không nên thiết kế getter cho binder một kiểu, getter cho service một kiểu, rồi kỳ vọng JavaBean Introspection tự biết lúc nào chọn phương thức nào.

## 27. Lỗi getter tạo một collection mới mỗi lần

Ví dụ:

~~~java
private final List<String> hosts = new ArrayList<>();

public List<String> getHosts() {
    return new ArrayList<>(hosts);
}
~~~

Nếu Binder mutate List mà getter trả về, thay đổi không được lưu vào field **hosts**. Dù method mang tên getHosts, nó không expose trạng thái cần cập nhật.

Có thể khắc phục bằng setter thật hoặc đổi sang constructor binding. Getter trả bản sao chỉ nên là một phần của một thiết kế setter-backed hoặc immutable được định nghĩa rõ, không phải nền tảng cho getter-only mutation.

## 28. Lỗi dùng collection không có public mutator đầy đủ

Ngoài List.of và Map.of, còn có:

~~~java
Arrays.asList(...)
Collections.singletonList(...)
Collections.emptyMap()
Collections.unmodifiableMap(...)
~~~

Những factory/wrapper này có khả năng thay đổi khác nhau. Một số không thể thay kích thước, một số không hỗ trợ put/remove, một số là view trên đối tượng khác.

Không dựa vào interface **List** hoặc **Map** để khẳng định mọi implementation đều hỗ trợ mutate. Với getter-only JavaBean binding, dùng loại mutable rõ ràng như ArrayList và LinkedHashMap nếu muốn binder cập nhật collection.

## 29. Lỗi collection vắng mặt nhưng bean vẫn khởi động

JavaBean:

~~~java
private List<String> hosts;
~~~

Record:

~~~java
public record GatewayProperties(List<String> hosts) {}
~~~

Nếu cấu hình không khai báo hosts, thuộc tính có thể là null tùy cách binding và default. Service sau đó gọi:

~~~java
properties.getHosts().size();
~~~

hoặc:

~~~java
properties.hosts().size();
~~~

có nguy cơ gặp **NullPointerException**.

Các lựa chọn:

- Cho mặc định rỗng và xử lý empty đúng nghĩa nghiệp vụ.
- Bắt buộc collection có ít nhất một phần tử bằng **@NotEmpty**.
- Đặt default host trong application.yml.
- Dùng compact constructor của record để normalize null.
- Với JavaBean, khởi tạo field bằng mutable empty collection.

Đừng dùng mặc định rỗng nếu thiếu hosts thực chất là lỗi triển khai bắt buộc phải dừng startup.

## 30. Lỗi list bị mất phần tử khi đổi profile

Nếu application.yml có ba worker, application-prod.yml chỉ chứa một worker, Spring Boot có thể dùng List từ nguồn profile có ưu tiên cao. Sau khi bật prod, số worker giảm từ ba thành một.

Đây không phải bằng chứng **List.copyOf** xóa phần tử hay setter clear nhầm. Nguyên nhân thuộc **quy tắc List replacement giữa các nguồn**.

Cách xác định:

1. Ghi lại các PropertySource liên quan.
2. Kiểm tra profile đang hoạt động.
3. Xem các file nào khai báo cùng path collection.
4. Xem nguồn ưu tiên cao nhất đang cung cấp List.
5. Xác nhận List cuối trong bean, không đoán bằng số dòng YAML gốc.

## 31. Lỗi map nhận key sai vì ký tự đặc biệt

Ví dụ key business là **us.east**:

~~~yaml
app:
  regions:
    us.east:
      endpoint: "https://east.example.test"
~~~

Khi Map value có cấu trúc nested, dấu chấm có thể bị hiểu là phần của property path. Nếu muốn giữ key có dấu chấm, dùng:

~~~yaml
app:
  regions:
    "[us.east]":
      endpoint: "https://east.example.test"
~~~

Vấn đề này không do Map mutable hay immutable. Dù Map cuối được copy thành Map bất biến, key đã bị phân tích sai trước đó vẫn sẽ không đúng như mong đợi.

## 32. Bảng quyết định: chọn mẫu nào?

| Yêu cầu | Mẫu nên cân nhắc | Điểm lưu ý |
| --- | --- | --- |
| JavaBean cần setter truyền thống | Mutable List/Map + getter/setter | Setter cho phép thay reference |
| JavaBean getter-only | Khởi tạo ArrayList/LinkedHashMap, getter trả chính field | Collection phải mutate được |
| Muốn cấu hình bất biến | Record constructor binding | Không cần setter |
| Muốn List/Map không bị service sửa | Record + List.copyOf/Map.copyOf | Cân nhắc null và deep immutability |
| List các bean con nhiều field | List<record> hoặc List<JavaBean> | Có index, validation phần tử |
| Danh sách các giá trị duy nhất | Set<T> | Không dùng khi thứ tự nghiệp vụ quan trọng |
| Dữ liệu theo key động | Map<String, Value> | Dùng bracket cho key đặc biệt |
| Cần default collection tùy chọn | Khởi tạo mutable trong JavaBean hoặc normalize constructor | Chọn rỗng hay có default rõ ràng |
| Cần bắt buộc collection không rỗng | @NotEmpty + @Validated | Thêm @Valid cho phần tử |
| Cần override List theo profile | Khai báo List hoàn chỉnh ở nguồn ưu tiên cao | Không kỳ vọng tự merge |
| Cần kết hợp các key Map | Map binding theo nhiều PropertySource | Key trùng chịu precedence |
| Cần thay đổi config khi ứng dụng chạy | Cơ chế runtime config/refresh riêng | Mutable List không tự refresh |

## 33. Kiểm thử getter-only mutable JavaBean

Có thể dùng **ApplicationContextRunner** của spring-boot-test để kiểm tra binding. Một ví dụ ý tưởng:

~~~java
import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsMutableGetterOnlyCollection() {
        runner.withPropertyValues(
                "app.gateway.hosts[0]=alpha.example.test",
                "app.gateway.hosts[1]=beta.example.test",
                "app.gateway.labels.owner=platform"
        ).run(context -> {
            GatewayProperties properties =
                    context.getBean(GatewayProperties.class);

            assertThat(properties.getHosts())
                    .containsExactly("alpha.example.test", "beta.example.test");
            assertThat(properties.getLabels())
                    .containsEntry("owner", "platform");
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(GatewayProperties.class)
    static class TestConfiguration {}
}
~~~

Trong test này, **GatewayProperties** là class getter-only mutable ở mục 4, có prefix **app.gateway**. Bộ test đưa property qua nguồn thử nghiệm, thay vì phải tạo file YAML hoặc biến môi trường hệ điều hành.

**Điều test thực sự chứng minh:** với version Spring Boot và class đang chạy, binder có điền đúng collection đã khởi tạo hay không. Đây là cách xác minh vững chắc khi dự án dùng một collection implementation đặc biệt hoặc muốn bỏ setter.

## 34. Kiểm thử immutable record và defensive copy

Đối với record, nên có một unit test thuần Java kiểm tra tính bất biến, không cần ApplicationContext:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.*;

class ImmutableGatewayPropertiesTest {

    @Test
    void defensiveCopiesPreventExternalMutation() {
        List<String> inputHosts = new ArrayList<>();
        inputHosts.add("alpha.example.test");

        Map<String, String> inputLabels = new LinkedHashMap<>();
        inputLabels.put("owner", "platform");

        GatewayProperties properties =
                new GatewayProperties(inputHosts, inputLabels);

        inputHosts.add("beta.example.test");
        inputLabels.put("region", "asia");

        assertThat(properties.hosts())
                .containsExactly("alpha.example.test");
        assertThat(properties.labels())
                .containsOnlyKeys("owner");

        assertThatThrownBy(() -> properties.hosts().add("other"))
                .isInstanceOf(UnsupportedOperationException.class);

        assertThatThrownBy(() -> properties.labels().put("x", "y"))
                .isInstanceOf(UnsupportedOperationException.class);
    }
}
~~~

Test này giả định GatewayProperties record có compact constructor thực hiện **List.copyOf** và **Map.copyOf** như mục 8.

Đây là bài test **hành vi Java object**, không phải bằng chứng binder đã đọc YAML đúng. Khi cần kiểm thử end-to-end binding, thêm một ApplicationContextRunner test riêng.

## 35. Kiểm thử List replacement qua nhiều PropertySource

Một bài kiểm thử có giá trị cho dự án dùng profile:

File nền:

~~~yaml
app:
  gateway:
    hosts:
      - alpha.example.test
      - beta.example.test
~~~

File profile prod:

~~~yaml
app:
  gateway:
    hosts:
      - production.example.test
~~~

Bật profile prod và assert số lượng host cuối cùng:

~~~java
assertThat(properties.hosts())
        .containsExactly("production.example.test");
~~~

Nếu test này thất bại vì một nguồn khác đã override, hãy ghi lại các PropertySource hoạt động. Không sửa code collection thành mutable để “cứu” một vấn đề thực chất đến từ thứ tự nguồn.

## 36. Nhận diện lỗi binding qua exception

Một số dấu hiệu:

| Triệu chứng | Nơi cần xem | Hướng xử lý |
| --- | --- | --- |
| UnsupportedOperationException | Immutable List/Map đang bị mutate? | Dùng mutable JavaBean hoặc constructor binding |
| Bean không có property trong List | Path/index bị sai? | Kiểm tra app.items[0].field |
| Getter-only List trống dù YAML có giá trị | Getter trả copy/unmodifiable? | Expose mutable collection thật hoặc thêm setter |
| Cannot bind properties | Sai kiểu item hoặc constructor? | Xem nguyên nhân lồng bên trong exception |
| List mất phần tử theo profile | List replacement | Xem source ưu tiên cao, khai báo đủ List |
| Map key bị tách ngoài ý muốn | Ký tự đặc biệt của key | Dùng bracket notation |
| NullPointerException khi truy cập collection | Field không có default | Normalize hoặc validation |
| Trùng bean configuration properties | Đăng ký cùng class nhiều cách | Chọn scan/enable nhất quán |
| Giá trị bean khác biến môi trường | Source precedence | Kiểm tra CLI, -D, env, config data |
| Setter không được gọi như kỳ vọng | Binder đang dùng constructor path/getter-only path? | Xác định binding strategy |
| Validation không chạy trên phần tử | Thiếu @Valid hoặc provider | Bổ sung cấu hình validation phù hợp |

Một thông báo “Failed to bind properties under ...” thường chứa đường dẫn property, loại Java đích và nguyên nhân chuyển đổi. Đọc phần root cause thay vì chỉ kết luận “Spring Boot không hỗ trợ immutable”.

## 37. Phân biệt binding, conversion và validation

Hãy xem ví dụ:

~~~yaml
app:
  workers:
    - name: indexing
      concurrency: many
~~~

Nếu Worker là:

~~~java
public record Worker(String name, int concurrency) {}
~~~

binder có thể đọc được đường dẫn **app.workers[0].concurrency**, nhưng **many** không chuyển thành int. Đây là **conversion failure**, không phải vấn đề setter hay mutability.

Nếu concurrency là **0** và có **@Min(1)**, lỗi thuộc **validation**. Nếu YAML đặt **concurrency** dưới cấp **app.queue.workers[0]** nhưng bean chờ **app.workers[0]**, đó là vấn đề **property path**.

Cách debug tốt là lần theo:

~~~text
PropertySource
   -> tên key đầy đủ
   -> giá trị raw
   -> chuyển sang kiểu phần tử
   -> tạo/cập nhật collection
   -> validation
   -> object Java cuối cùng
~~~

Việc thêm một setter không thể sửa lỗi sai kiểu dữ liệu hoặc sai cấp YAML.

## 38. Diagnostic qua Environment

Một ví dụ đọc những key không nhạy cảm:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ConfigProbe implements ApplicationRunner {

    private final Environment environment;

    ConfigProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("first host = "
                + environment.getProperty("app.gateway.hosts[0]"));
        System.out.println("owner = "
                + environment.getProperty("app.gateway.labels.owner"));
    }
}
~~~

Đây chỉ là cách đọc các property cụ thể trong Spring Environment. Nó không thay thế việc xem collection cuối được bind vào bean qua getter hoặc record accessor.

Nếu Environment nhận giá trị đúng mà bean không có nó, hãy xét binding strategy, mutability, constructor, conversion và validation.

### 38.1. Liệt kê tên PropertySource

Trong lúc debug môi trường, có thể dùng ConfigurableEnvironment:

~~~java
for (org.springframework.core.env.PropertySource<?> source
        : environment.getPropertySources()) {
    System.out.println(source.getName());
}
~~~

Đoạn này giả định **environment** có kiểu **ConfigurableEnvironment**. Chỉ in tên các nguồn, không in toàn bộ key/value vì collection cấu hình có thể chứa token hoặc secret.

Spring Boot Actuator, khi được cấu hình bảo vệ, có thể hỗ trợ truy nguyên nguồn thuộc tính. Không công khai endpoint chẩn đoán chỉ để kiểm tra danh sách host.

## 39. Một cấu hình hoàn chỉnh để triển khai

Ví dụ file nền:

~~~yaml
app:
  notifications:
    channels:
      - email
      - webhook
    templates:
      welcome: "welcome-v1"
      alert: "alert-v2"
    targets:
      - name: primary
        endpoint: "https://notify.example.test"
        timeout: 3s
~~~

Một record bất biến:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.notifications")
public record NotificationProperties(
        List<String> channels,
        Map<String, String> templates,
        List<Target> targets
) {
    public NotificationProperties {
        channels = channels == null
                ? List.of()
                : List.copyOf(channels);
        templates = templates == null
                ? Map.of()
                : Map.copyOf(templates);
        targets = targets == null
                ? List.of()
                : List.copyOf(targets);
    }

    public record Target(
            String name,
            String endpoint,
            Duration timeout
    ) {}
}
~~~

Các đường dẫn chính:

~~~text
app.notifications.channels[0]
app.notifications.channels[1]
app.notifications.templates.welcome
app.notifications.templates.alert
app.notifications.targets[0].name
app.notifications.targets[0].endpoint
app.notifications.targets[0].timeout
~~~

Ví dụ biến môi trường cho một target:

~~~text
APP_NOTIFICATIONS_TARGETS_0_NAME
APP_NOTIFICATIONS_TARGETS_0_ENDPOINT
APP_NOTIFICATIONS_TARGETS_0_TIMEOUT
~~~

Lưu ý: nếu triển khai chỉ cung cấp lại phần tử target[0] từ env có độ ưu tiên cao, hãy kiểm tra toàn bộ List targets cuối cùng. Không mặc định các trường không khai báo ở env sẽ được hợp nhất từ file nền.

### 39.1. Khi chọn JavaBean thay vì record

Nếu hệ thống legacy yêu cầu setters, có thể giữ JavaBean để binding, rồi tạo một đối tượng immutable riêng cho service tiêu thụ. Tuy nhiên, phải làm rõ trách nhiệm ai có quyền sửa object JavaBean sau startup.

Ví dụ một bước chuyển đổi:

~~~java
public record NotificationSnapshot(List<String> channels) {
    public NotificationSnapshot {
        channels = channels == null
                ? List.of()
                : List.copyOf(channels);
    }
}
~~~

Một service cấu hình có thể tạo snapshot từ JavaBean đã được bind, rồi chỉ truyền NotificationSnapshot cho các module khác. Hướng này cho phép giữ compatibility với JavaBean binding mà không expose mutable List rộng rãi.

## 40. Bài thực hành 1: getter-only mutable

Cho YAML:

~~~yaml
app:
  tags:
    names:
      - green
      - blue
~~~

Hãy xây một JavaBean với prefix **app.tags**, không có setter cho names nhưng bind được dữ liệu qua collection đã khởi tạo.

Đáp án minh họa:

~~~java
@ConfigurationProperties(prefix = "app.tags")
public class TagProperties {

    private final List<String> names = new ArrayList<>();

    public List<String> getNames() {
        return names;
    }
}
~~~

Giải thích: getter trả chính ArrayList mutable. Nếu đổi thành **List.of()**, không thể áp dụng cùng giả định cập nhật bằng mutation.

## 41. Bài thực hành 2: immutable record

Cho YAML:

~~~yaml
app:
  tags:
    names:
      - green
      - blue
~~~

Viết record không có setter, bảo vệ khỏi code ngoài gọi add:

~~~java
@ConfigurationProperties(prefix = "app.tags")
public record TagProperties(List<String> names) {

    public TagProperties {
        names = names == null ? List.of() : List.copyOf(names);
    }
}
~~~

Khi code khác gọi:

~~~java
properties.names().add("red");
~~~

List do copyOf tạo ra không hỗ trợ add. Đây là một phần hợp đồng bất biến của bean.

## 42. Bài thực hành 3: getter trả copy

Một bạn viết:

~~~java
private final Map<String, String> labels = new LinkedHashMap<>();

public Map<String, String> getLabels() {
    return new LinkedHashMap<>(labels);
}
~~~

Bạn ấy không viết setter. Tại sao đây không phải mẫu getter-only binding nên dùng?

Vì mỗi lần getter trả một Map khác. Binder nếu ghi vào Map đó thì không nhất thiết cập nhật field **labels** ban đầu. Cách sửa là trả trực tiếp labels nếu chọn mutable getter-only, hoặc chuyển sang setter/constructor binding và defensive copy để đạt yêu cầu chỉ đọc.

## 43. Bài thực hành 4: List vs Map precedence

File nền:

~~~yaml
app:
  servers:
    - alpha
    - beta
  labels:
    owner: platform
    region: global
~~~

File profile prod:

~~~yaml
app:
  servers:
    - production
  labels:
    region: asia
    tier: critical
~~~

Hãy dự đoán:

~~~text
servers = [production]

labels.owner  = platform
labels.region = asia
labels.tier   = critical
~~~

Trong cơ chế binding thông thường, List có xu hướng được **thay thế** bởi List của nguồn ưu tiên cao, còn Map có thể **kết hợp** các key. Giải thích này độc lập với việc object đích sau cùng là JavaBean mutable hay record immutable.

## 44. Bài thực hành 5: Map có key chứa dấu chấm

YAML chưa rõ ý:

~~~yaml
app:
  tenant-configs:
    tenant.eu:
      enabled: true
~~~

Nếu **tenant.eu** cần là nguyên một key Map<String, TenantConfig>, dùng:

~~~yaml
app:
  tenant-configs:
    "[tenant.eu]":
      enabled: true
~~~

Viết record:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        Map<String, TenantConfig> tenantConfigs
) {
    public record TenantConfig(boolean enabled) {}
}
~~~

Sau binding, key mong đợi là **tenant.eu**. Tính mutability của Map không thay đổi quy tắc nhận diện key.

## 45. Bài thực hành 6: chọn setter hay constructor

Một người yêu cầu:

- Cấu hình có List<Region>.
- Sau startup các service chỉ được đọc.
- Không muốn setter trong public API.
- Region có endpoint và timeout.
- Không cần refresh runtime.

Thiết kế phù hợp:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(List<Region> regions) {

    public AppProperties {
        regions = regions == null
                ? List.of()
                : List.copyOf(regions);
    }

    public record Region(
            String endpoint,
            java.time.Duration timeout
    ) {}
}
~~~

Đăng ký qua @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties. Đây là constructor binding, không cần JavaBean getter/setter. Có thể thêm validation nếu danh sách phải không rỗng hoặc endpoint phải hợp lệ.

## 46. Quy trình lựa chọn thiết kế trước khi code

Khi bắt đầu một nhóm Collection/Map, hãy quyết định:

1. **Collection có cần thay đổi sau khởi động không?** Nếu không, ưu tiên mô hình bất biến.
2. **Có dùng JavaBean/setter binding vì legacy không?** Nếu có, getter-only chỉ nên dùng với collection thực sự mutable và đã khởi tạo.
3. **Đang dùng List hay Set hay Map?** Chọn dựa trên ý nghĩa thứ tự, uniqueness và key động.
4. **Phần tử là scalar hay object?** Nếu object, thiết kế kiểu element có đường khởi tạo rõ ràng.
5. **Default mong muốn là gì?** Vắng mặt, rỗng và danh sách có giá trị mặc định không đồng nghĩa.
6. **Có bắt buộc ít nhất một phần tử không?** Dùng validation phù hợp.
7. **Có nhiều nguồn cùng khai báo collection không?** Hiểu List replacement và Map merging.
8. **Có key Map đặc biệt không?** Dùng bracket notation khi cần.
9. **Có thông tin nhạy cảm không?** Tránh log toString của record chứa secret.
10. **Có test về binding và immutability không?** Kiểm tra cả input PropertySource lẫn hành vi object Java.

Nếu một thiết kế vừa đòi getter-only, vừa đòi collection bất biến ngay từ trước khi binder chạy, đó là tín hiệu nên xem lại chiến lược: **bind bằng constructor vào immutable record** thường diễn đạt mục tiêu tốt hơn.

## 47. Ghi nhớ

- **Mutable collection** cho phép cập nhật phần tử; **immutable/unmodifiable collection** không cho phép các thao tác đó. Một field **final List** vẫn có thể trỏ tới ArrayList mutable.
- Với **JavaBean binding**, setter thường là đường rõ ràng để gán collection mới. Một **List/Map đã khởi tạo, mutable, có getter trả đúng object** có thể được bind mà không cần setter trong các trường hợp được hỗ trợ.
- **Getter trả List.of, Map.of, unmodifiable wrapper hoặc bản sao** không phải mẫu getter-only mutable binding đáng tin cậy.
- Với **constructor binding/record**, binder truyền List/Map qua constructor, không cần setter. Muốn bảo vệ object sau khởi tạo, dùng defensive copy có kiểm soát.
- **Record có component List/Map không tự bảo đảm deep immutability**; phần tử bên trong cũng cần được xem xét.
- **List** biểu diễn theo index và thường chịu quy tắc thay thế giữa PropertySource; **Map** có thể kết hợp key từ nhiều nguồn. Mutability của object Java không quyết định precedence đó.
- **Vắng mặt**, **null** và **collection rỗng** là các tình huống khác nhau. Thiết kế default và validation theo đúng yêu cầu nghiệp vụ.
- Nếu muốn collection bắt buộc có nội dung, dùng **@NotEmpty**; với object con cần xét **@Valid** và constraints của từng phần tử.
- Khi runtime sai, kiểm tra theo chuỗi **tên property → PropertySource → kiểu dữ liệu → cơ chế bind → collection instance → validation**.
- Nếu cấu hình chỉ đọc sau startup, record với constructor binding và defensive copy thường giúp giảm rủi ro service khác vô tình mutate cấu hình.

Điểm quan trọng nhất là **getter/setter là một phần của chiến lược tạo và cập nhật object, còn mutable/immutable là đặc tính của collection được đặt trong object**. Tách hai khái niệm đó ra sẽ giúp chọn đúng JavaBean binding hoặc constructor binding, tránh các lỗi khó đoán khi cấu hình List, Set và Map trong Spring Boot.
