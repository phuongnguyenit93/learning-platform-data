# Phân biệt hằng giữ tham chiếu với đối tượng bất biến sâu

Trong Java, từ khóa final trên một trường tham chiếu chỉ ngăn trường đó được gán sang một tham chiếu khác sau khi đã khởi tạo. Nó không làm cho đối tượng được tham chiếu trở nên bất biến. Một đối tượng chỉ bất biến sâu khi trạng thái của chính nó và toàn bộ trạng thái có thể truy cập thông qua nó không thể bị thay đổi từ bất kỳ alias nào.

Sự khác biệt này rất quan trọng khi chia sẻ dữ liệu giữa nhiều thread, xây dựng cache, giữ cấu hình dùng chung và áp dụng Lazy Constants của Java 26. LazyConstant bảo đảm nội dung được gán tối đa một lần và có thể được JVM tối ưu như hằng số; bản thân đối tượng T mà nó giữ vẫn có thể là mutable. Vì vậy, hằng giữ tham chiếu, giá trị được khởi tạo trễ và đối tượng bất biến sâu là ba khái niệm cần phân biệt.

## 1. final khóa biến tham chiếu, không khóa trạng thái đối tượng

Ví dụ:

~~~java
import java.util.ArrayList;
import java.util.List;

public class FinalReferenceDemo {
    private static final List<String> NAMES = new ArrayList<>();

    public static void main(String[] args) {
        NAMES.add("An");
        NAMES.add("Bình");

        System.out.println(NAMES);

        // Không hợp lệ: không thể gán NAMES sang một List khác.
        // NAMES = new ArrayList<>();
    }
}
~~~

NAMES là trường final, nên sau khi được gán, trường luôn giữ cùng một tham chiếu đến đối tượng List. Nhưng lời gọi add vẫn thay đổi trạng thái của ArrayList đó.

Có thể hiểu theo hai lớp:

- **Tham chiếu**: final ngăn việc gán lại trường để trỏ sang đối tượng khác.
- **Đối tượng**: các phương thức của đối tượng vẫn có thể thay đổi dữ liệu nội bộ nếu lớp cho phép.

Cùng nguyên tắc này áp dụng cho mảng, Date, StringBuilder, Map, Set, các đối tượng cấu hình và các lớp tự viết. Khai báo final chỉ tác động lên biến hoặc trường được khai báo.

### 1.1. final không phải deep freeze

~~~java
final class Account {
    private final String id;
    private final List<String> roles;

    Account(String id, List<String> roles) {
        this.id = id;
        this.roles = roles;
    }

    List<String> roles() {
        return roles;
    }
}
~~~

Trường id tham chiếu đến String, một kiểu bất biến. Trường roles là final nhưng tham chiếu đến List có thể thay đổi. Ngoài ra, constructor giữ nguyên tham chiếu do caller truyền vào và accessor trả trực tiếp tham chiếu đó ra ngoài. Bất kỳ bên nào giữ alias của list đều có thể thêm hoặc xóa role.

~~~java
List<String> input = new ArrayList<>();
input.add("reader");

Account account = new Account("A-01", input);

input.add("admin");                 // Thay đổi trạng thái nhìn thấy từ account.
account.roles().add("operator");    // Caller cũng sửa được trực tiếp.
~~~

Đây là ví dụ về tham chiếu final nhưng trạng thái đối tượng không được đóng gói và không bất biến.

## 2. Ba khái niệm cần tách biệt

| Khái niệm | Điều được bảo đảm | Điều không được bảo đảm |
|---|---|---|
| final reference | Trường hoặc biến không được gán lại sau khi khởi tạo | Đối tượng được tham chiếu không tự động bất biến |
| Shallow immutability | Lớp giữ nguyên các tham chiếu hoặc nội dung ở lớp ngoài sau khi khởi tạo | Đối tượng con hoặc phần tử bên trong có thể vẫn mutable |
| Deep immutability | Trạng thái của toàn bộ object graph có thể truy cập không thể thay đổi | Không tự có được chỉ bằng cách thêm final vào mọi trường |

Deep immutability phụ thuộc vào toàn bộ object graph, không chỉ vào khai báo của lớp ngoài. Nếu một đối tượng giữ List, và list giữ các đối tượng mutable, thì việc không thể thay thế trường List vẫn chưa đủ.

Một object graph được xem là bất biến sâu khi:

- Mọi trường trạng thái đều được khởi tạo một lần và không có phương thức thay đổi trạng thái.
- Không giữ hoặc để lộ alias có thể sửa các đối tượng con.
- Các thành phần được tham chiếu cũng bất biến sâu, hoặc được sao chép/phòng vệ để caller không thể sửa trạng thái nội bộ.
- Mảng và collection không bị trả trực tiếp ra ngoài nếu caller có thể sửa chúng.
- Constructor không để lộ this trước khi khởi tạo hoàn tất.

Java không có từ khóa hoặc annotation phổ quát để compiler tự xác nhận một object graph bất biến sâu. Đây là thuộc tính của thiết kế và hợp đồng API.

## 3. Collection không sửa được chưa chắc bất biến sâu

Java có nhiều API tạo collection không cho phép caller sửa cấu trúc. Tuy nhiên, cần phân biệt unmodifiable view, unmodifiable snapshot và tính bất biến của phần tử.

### 3.1. Collections.unmodifiableList tạo view

~~~java
List<String> source = new ArrayList<>();
source.add("read");

List<String> view = java.util.Collections.unmodifiableList(source);

// view.add("write"); // UnsupportedOperationException
source.add("write");

System.out.println(view); // [read, write]
~~~

view chặn thao tác sửa thông qua chính view đó, nhưng vẫn phản ánh thay đổi từ source. Nó là một lớp bọc không cho sửa qua một đường truy cập cụ thể, không phải bản sao độc lập của dữ liệu.

### 3.2. List.copyOf tạo snapshot không sửa được

~~~java
List<String> source = new ArrayList<>();
source.add("read");

List<String> snapshot = List.copyOf(source);
source.add("write");

System.out.println(snapshot); // [read]
~~~

List.copyOf tạo collection không sửa được và không phản ánh thay đổi cấu trúc về sau của source. Đây là lựa chọn tốt để phòng vệ với collection đầu vào nếu phần tử cũng là kiểu bất biến.

Tuy nhiên, List.copyOf chỉ sao chép cấu trúc collection. Nó không sao chép sâu từng phần tử. Nếu phần tử là đối tượng mutable, caller vẫn có thể thay đổi đối tượng đó qua alias khác.

~~~java
final class Permission {
    private String name;

    Permission(String name) {
        this.name = name;
    }

    void rename(String newName) {
        this.name = newName;
    }

    String name() {
        return name;
    }
}

List<Permission> input = new ArrayList<>();
Permission read = new Permission("read");
input.add(read);

List<Permission> copy = List.copyOf(input);
read.rename("admin");

System.out.println(copy.get(0).name()); // admin
~~~

Collection không cho thêm/xóa phần tử, nhưng trạng thái của phần tử Permission vẫn thay đổi. Vì vậy, collection không sửa được không đồng nghĩa với deep immutability.

## 4. Record cũng chỉ bất biến nông nếu thành phần có thể mutable

Record tự sinh các component field final và accessor tương ứng. Điều đó giúp record phù hợp để mô hình hóa dữ liệu, nhưng record không tự động làm bất biến các đối tượng được tham chiếu.

Ví dụ:

~~~java
import java.util.List;

record UserProfile(String name, List<String> tags) { }
~~~

Hai component field là final. Tuy nhiên, constructor mặc định nhận nguyên tham chiếu List từ caller và accessor tags() trả lại tham chiếu đó. Nếu list có thể sửa, trạng thái quan sát được của UserProfile vẫn thay đổi.

Có thể tạo snapshot cho thành phần collection trong compact constructor:

~~~java
import java.util.List;

record UserProfile(String name, List<String> tags) {
    UserProfile {
        tags = List.copyOf(tags);
    }
}
~~~

Với ví dụ này, String là bất biến và tags là snapshot không sửa được. Object graph của UserProfile có thể được xem là bất biến sâu theo các thành phần đang có.

Nếu record chứa List<Permission> mà Permission mutable, List.copyOf vẫn chỉ bảo vệ cấu trúc list. Cần làm cho Permission bất biến sâu hoặc chuyển các phần tử thành kiểu dữ liệu bất biến riêng trước khi lưu.

## 5. Sao chép phòng vệ với mảng

Mảng trong Java luôn có thể sửa phần tử. Một trường final chứa mảng chỉ khóa tham chiếu mảng:

~~~java
final class Digest {
    private final byte[] value;

    Digest(byte[] value) {
        this.value = value;
    }

    byte[] value() {
        return value;
    }
}
~~~

Caller có thể sửa mảng đầu vào sau khi tạo Digest hoặc sửa mảng lấy từ accessor. Cần sao chép cả lúc nhận và lúc trả dữ liệu:

~~~java
final class Digest {
    private final byte[] value;

    Digest(byte[] value) {
        this.value = value.clone();
    }

    byte[] value() {
        return value.clone();
    }
}
~~~

Với byte[] như ví dụ, clone sao chép toàn bộ phần tử byte vì byte là primitive. Với Object[], clone chỉ sao chép mảng ngoài; các tham chiếu đến phần tử vẫn trỏ đến cùng đối tượng. Nếu phần tử có thể mutable, cần sao chép sâu hoặc chuyển chúng thành kiểu bất biến.

## 6. Cách thiết kế một object bất biến sâu

Có thể dùng quy trình sau khi xây dựng lớp cấu hình, dữ liệu nghiệp vụ hoặc đối tượng dùng chung giữa nhiều thread.

1. Khai báo các trường trạng thái là private final.
2. Khởi tạo đầy đủ trong constructor hoặc factory trước khi đối tượng được chia sẻ.
3. Sao chép phòng vệ dữ liệu đầu vào nếu caller có thể tiếp tục sửa nó.
4. Không cung cấp setter hoặc phương thức thay đổi trạng thái.
5. Không trả trực tiếp mảng, collection hoặc đối tượng mutable nội bộ.
6. Với collection, tạo snapshot không sửa được và bảo đảm phần tử cũng bất biến sâu.
7. Với mảng, clone khi nhận và khi trả; nếu là mảng đối tượng, đánh giá nhu cầu sao chép từng phần tử.
8. Không để this thoát khỏi constructor qua callback, đăng ký listener hoặc thread trước khi khởi tạo hoàn tất.

Ví dụ một cấu hình bất biến sâu:

~~~java
import java.util.List;
import java.util.Objects;

record Endpoint(String host, int port) {
    Endpoint {
        Objects.requireNonNull(host);
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("Invalid port");
        }
    }
}

record ServiceConfig(String name, List<Endpoint> endpoints) {
    ServiceConfig {
        Objects.requireNonNull(name);
        endpoints = List.copyOf(endpoints);
    }
}
~~~

Endpoint chỉ chứa String và int; cả hai không thể bị sửa trạng thái. ServiceConfig giữ một snapshot List không sửa được của các Endpoint bất biến. Không có đường truy cập nào cho caller thay đổi cấu trúc list hoặc trạng thái endpoint, nên object graph này bất biến sâu theo mô hình dữ liệu đã định nghĩa.

## 7. LazyConstant giữ giá trị một lần, không làm đối tượng bên trong bất biến sâu

Lazy Constants là cải tiến thư viện trong Java 26. API java.lang.LazyConstant được giới thiệu dưới dạng preview trong JEP 526 (Second Preview). Một LazyConstant ban đầu chưa có nội dung; lần gọi get() đầu tiên thực hiện computing function và lưu kết quả. Những lần gọi sau trả lại cùng nội dung đã được khởi tạo.

~~~java
import java.lang.LazyConstant;

final class SharedSettings {
    private static final LazyConstant<ServiceConfig> CONFIG =
        LazyConstant.of(SharedSettings::loadConfig);

    static ServiceConfig config() {
        return CONFIG.get();
    }

    private static ServiceConfig loadConfig() {
        return new ServiceConfig(
            "billing",
            List.of(new Endpoint("api.example.test", 443))
        );
    }
}
~~~

Ở đây có hai lớp bảo đảm:

- LazyConstant bảo đảm nội dung được thiết lập tối đa một lần; các thread cạnh tranh gọi get() chỉ có một thread chạy computing function, những thread còn lại chờ kết quả.
- ServiceConfig phải tự bảo đảm bất biến sâu nếu ứng dụng muốn chia sẻ cấu hình mà không cần khóa đồng bộ cho mọi thao tác đọc.

Nếu thay ServiceConfig bằng một ArrayList hoặc một đối tượng mutable, LazyConstant vẫn giữ cùng tham chiếu đó sau khi khởi tạo. Các lời gọi get() trả lại cùng đối tượng; chúng không tạo bản sao và không khóa các phương thức sửa trạng thái của đối tượng.

Ví dụ sau minh họa sự khác biệt:

~~~java
import java.lang.LazyConstant;
import java.util.ArrayList;
import java.util.List;

public class ShallowLazyDemo {
    private static final LazyConstant<List<String>> TAGS =
        LazyConstant.of(() -> new ArrayList<>(List.of("stable")));

    public static void main(String[] args) {
        List<String> first = TAGS.get();
        List<String> second = TAGS.get();

        System.out.println(first == second); // true

        first.add("changed");
        System.out.println(second);          // [stable, changed]
    }
}
~~~

LazyConstant giữ cùng tham chiếu List sau lần khởi tạo đầu tiên. Việc thêm phần tử vẫn thay đổi List vì ArrayList mutable. Tính ổn định của holder không biến giá trị thành immutable.

### 7.1. Thread safety không đồng nghĩa deep immutability

LazyConstant bảo đảm việc khởi tạo là atomic và at most once. Việc khởi tạo cùng nội dung được thiết lập trước khi các thread khác đọc giá trị, theo quan hệ happens-before được API quy định. Điều này giúp công bố an toàn đối tượng vừa tạo, bao gồm các trường final của nó.

Nhưng sau khi get() trả về, nếu đối tượng được giữ có phương thức thay đổi trạng thái thì các thread vẫn có thể cùng sửa nó. Những thao tác đó cần thiết kế đồng bộ riêng hoặc loại bỏ bằng cách dùng kiểu bất biến sâu.

JVM có thể constant-fold nội dung LazyConstant khi holder được tham chiếu trực tiếp từ trường static final hoặc đi qua chuỗi trường được JVM tin cậy. Đây là quyền tối ưu hóa của implementation, không phải cam kết rằng mọi LazyConstant ở mọi vị trí đều được thay bằng hằng trong mã máy. Đặt holder ở vị trí phù hợp và đo workload thực tế trước khi kết luận có lợi ích hiệu năng.

LazyConstant giữ tham chiếu mạnh đến nội dung sau khi khởi tạo. Nội dung không thể được xóa khỏi holder; nếu holder sống lâu hơn nhu cầu của ứng dụng, đối tượng lớn hoặc tài nguyên được giữ lại có thể làm tăng bộ nhớ sử dụng. Computing function cũng chạy trên thread đầu tiên gọi get(); nếu hàm chặn vô thời hạn, các thread khác đang chờ cùng holder có thể chặn theo.

Không nên diễn giải guarantee của LazyConstant thành:

- Mọi trường bên trong đối tượng đều tự động final.
- Các collection bên trong tự động chuyển thành unmodifiable.
- Mọi lần truy cập đến đối tượng đều được khóa.
- Mọi phương thức của đối tượng đều thread-safe.

Bảo đảm chỉ áp dụng cho việc thiết lập nội dung của LazyConstant. Đối tượng T phải tự đáp ứng hợp đồng về tính bất biến hoặc thread safety của nó.

## 8. Trạng thái preview và thay đổi API theo JDK

LazyConstant chưa phải API chính thức trong Java 26. Cần bật preview khi biên dịch và chạy chương trình. Trạng thái hiện hành đến ngày 27-11-2026:

| Phiên bản JDK | JEP và trạng thái | Ghi chú |
|---|---|---|
| JDK 25 | JEP 502, Stable Values (Preview) | Tên và thiết kế API preview ban đầu; không dùng tên StableValue cho code Java 26 |
| JDK 26 | JEP 526, Lazy Constants (Second Preview) | Có java.lang.LazyConstant; preview API |
| JDK 27 | JEP 531, Lazy Constants (Third Preview) | Vẫn preview; API đã được tinh gọn |

Ở JDK 26, có các phương thức isInitialized() và orElse() trong API preview. Trong JDK 27, hai phương thức này đã bị loại bỏ. Vì vậy, ví dụ trong bài chỉ sử dụng of() và get(), là các thao tác cốt lõi tiếp tục có trong JDK 27. Không sao chép code dùng các API preview cũ mà không kiểm tra Javadoc của đúng JDK mục tiêu.

JDK 27 cũng thay đổi cách xử lý lỗi của computing function: nếu hàm trả về null hoặc ném unchecked exception, LazyConstant chuyển sang error state; lần get() gây lỗi nhận NoSuchElementException có nguyên nhân, và các lần get() sau tiếp tục nhận NoSuchElementException mà không chạy lại computing function. Hành vi này khác với đặc tả JDK 26 preview, trong đó lỗi tính toán có thể để holder chưa khởi tạo và một lần get() sau có thể thử tính toán lại. Không xây dựng logic retry dựa vào hành vi của một bản preview cũ.

### 8.1. Biên dịch và chạy với JDK 26

Với file SharedSettings.java hoặc ShallowLazyDemo.java:

~~~sh
javac --enable-preview --release 26 SharedSettings.java
java --enable-preview SharedSettings
~~~

Cả compiler và JVM đều phải bật preview của cùng bản JDK. Nếu chạy bằng JDK 26, dùng --release 26 và --enable-preview. Không lấy class file được biên dịch bằng preview của JDK 26 để chạy bằng JDK 27 hoặc JDK khác.

### 8.2. Kiểm tra với JDK 27 hiện hành

JDK 27 vẫn cung cấp LazyConstant dưới dạng preview lần thứ ba. Biên dịch lại source bằng chính JDK 27:

~~~sh
javac --enable-preview --release 27 SharedSettings.java
java --enable-preview SharedSettings
~~~

Không dùng lại class file preview từ JDK 26. Đặc biệt, code gọi isInitialized() hoặc orElse() theo API JDK 26 sẽ không biên dịch với API JDK 27.

Vì LazyConstant vẫn là preview, không xem nó là hợp đồng API ổn định cho thư viện hoặc ứng dụng production cần nâng cấp JDK độc lập. Nếu dùng để thử nghiệm, khóa phiên bản JDK, bật preview nhất quán trong IDE, build, test và runtime, rồi kiểm tra lại API khi chuyển JDK.

## 9. Lựa chọn thay thế khi không dùng preview

Với ứng dụng production cần API ổn định, hãy chọn cách khởi tạo phù hợp với yêu cầu:

### 9.1. Khởi tạo eager bằng static final

~~~java
final class AppConfig {
    static final ServiceConfig CONFIG = loadConfig();

    private AppConfig() { }

    private static ServiceConfig loadConfig() {
        return new ServiceConfig(
            "billing",
            List.of(new Endpoint("api.example.test", 443))
        );
    }
}
~~~

Đơn giản, dễ hiểu và dùng API ổn định. Đổi lại, class initialization tạo cấu hình khi lớp được khởi tạo, dù ứng dụng có sử dụng giá trị đó hay không.

### 9.2. Initialization-on-demand holder

~~~java
final class AppConfig {
    private AppConfig() { }

    static ServiceConfig config() {
        return Holder.CONFIG;
    }

    private static class Holder {
        static final ServiceConfig CONFIG = loadConfig();
    }

    private static ServiceConfig loadConfig() {
        return new ServiceConfig(
            "billing",
            List.of(new Endpoint("api.example.test", 443))
        );
    }
}
~~~

Class Holder chỉ được khởi tạo khi config() được gọi lần đầu. Cơ chế khởi tạo class của JVM bảo đảm việc khởi tạo thread-safe. Đây là lựa chọn ổn định cho singleton hoặc cấu hình khởi tạo trễ không cần API preview.

Cả hai cách trên vẫn cần ServiceConfig được thiết kế bất biến sâu nếu muốn chia sẻ an toàn. Cách khởi tạo trễ không thay thế thiết kế dữ liệu bất biến.

## 10. Lỗi thiết kế thường gặp

| Cách hiểu sai | Thực tế | Cách xử lý |
|---|---|---|
| Trường final làm đối tượng bất biến | Chỉ khóa việc gán lại tham chiếu | Kiểm tra mọi đường sửa trạng thái của đối tượng |
| Record tự động deep immutable | Component field final nhưng component object có thể mutable | Sao chép phòng vệ và bảo đảm component bất biến |
| Collections.unmodifiableList là bản sao | Đây là view không sửa được, vẫn phản ánh thay đổi từ collection nền | Dùng List.copyOf khi cần snapshot cấu trúc |
| List.copyOf sao chép sâu | Chỉ tạo snapshot cấu trúc; phần tử vẫn được dùng chung | Dùng phần tử bất biến hoặc sao chép từng phần tử |
| Mảng final không thể bị sửa | Có thể sửa từng phần tử qua mọi alias | Clone khi nhận và khi trả; clone sâu nếu là mảng object |
| LazyConstant làm T immutable | Chỉ đảm bảo nội dung holder được thiết lập một lần | Thiết kế T bất biến sâu hoặc tự quản lý đồng bộ |
| LazyConstant get() luôn là cache thread-safe cho mọi trạng thái bên trong | Chỉ quá trình khởi tạo holder được bảo đảm | Không sửa T sau khi công bố hoặc đồng bộ riêng |
| Preview của JDK 26 có thể dùng nguyên trạng trên JDK 27 | Preview API có thể thay đổi giữa các bản phát hành | Biên dịch và chạy bằng đúng JDK mục tiêu; kiểm tra Javadoc |
| LazyConstant đã là API production ổn định | JDK 26 và JDK 27 đều ghi nhận API preview | Dùng phương án khởi tạo ổn định nếu không chấp nhận preview |

## 11. Checklist đánh giá một hằng tham chiếu

- [ ] Trường final chỉ được xem là khóa tham chiếu, không mặc định là khóa trạng thái đối tượng.
- [ ] Đã xác định mọi alias giữ tham chiếu đến đối tượng và các thành phần con.
- [ ] Collection đầu vào đã được sao chép phòng vệ nếu caller có thể sửa.
- [ ] Collection trả ra không để lộ trạng thái nội bộ có thể thay đổi.
- [ ] Phần tử của collection cũng bất biến hoặc được sao chép sâu.
- [ ] Mảng được clone khi nhận và khi trả.
- [ ] Record được đánh giá theo từng component, không chỉ theo modifier final.
- [ ] Constructor không để lộ this trước khi hoàn tất khởi tạo.
- [ ] Nếu chia sẻ giữa thread, đã phân biệt safe publication với thread safety của các thao tác về sau.
- [ ] Nếu dùng LazyConstant, đã xác nhận JDK và preview version; không giả định nó làm đối tượng T bất biến sâu.
- [ ] Với production không bật preview, đã cân nhắc static final hoặc initialization-on-demand holder.

## Tài liệu tham khảo

- [Java SE 26 LazyConstant API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/LazyConstant.html): nội dung chỉ được thiết lập tối đa một lần, thread safety, happens-before và preview API.
- [JEP 526 — Lazy Constants (Second Preview)](https://openjdk.org/jeps/526): thiết kế LazyConstant trong JDK 26.
- [Java SE 27 LazyConstant API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/LazyConstant.html): API và xử lý lỗi trong preview JDK 27.
- [JEP 531 — Lazy Constants (Third Preview)](https://openjdk.org/jeps/531): thay đổi trong preview JDK 27.
- [Java SE 26 List API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html): List.of, List.copyOf và collection không sửa được.
- [Java SE 26 Record Classes](https://docs.oracle.com/en/java/javase/26/language/records.html): record components và đặc tính của record.
- [Java Language Specification, Chapter 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se26/html/jls-17.html): final field semantics và memory model.
- [JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): xác nhận Lazy Constants là third preview trong JDK 27.

