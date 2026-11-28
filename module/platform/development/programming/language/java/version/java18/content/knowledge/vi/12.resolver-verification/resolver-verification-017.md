# Thực hành provider ánh xạ tên cho fixture cục bộ với báo cáo kết quả theo từng JVM

> **Chương:** Kiểm chứng resolver  
> **Phạm vi:** Java 18 trở lên; thực hành `java.net.spi.InetAddressResolverProvider` (Internet-Address Resolution SPI, JEP 418) trên phiên bản JDK đang sử dụng.

## 1. Mục tiêu và tình huống

Bạn cần kiểm thử thành phần sử dụng `InetAddress.getAllByName(...)` mà không phụ thuộc vào DNS bên ngoài. Thay vì cấu hình DNS thật hoặc sửa tệp `hosts` của hệ điều hành, hãy cung cấp **một resolver bằng SPI** để ánh xạ hostname cố định của bài kiểm thử sang địa chỉ loopback. Mỗi lần khởi động JVM sẽ mang một giá trị fixture riêng, thực thi tra cứu và xuất một dòng báo cáo có thể đối chiếu.

Bài thực hành này tập trung vào khả năng kiểm chứng trên JDK hiện đại: đăng ký `InetAddressResolverProvider`, cài đặt `InetAddressResolver`, dùng `Configuration.builtinResolver()` cho hostname không thuộc fixture và xác nhận kết quả trong **các tiến trình JVM độc lập**. Không sử dụng các SPI nội bộ hoặc kỹ thuật can thiệp DNS đã lỗi thời.

**Kết quả cần đạt:**

- Hostname `orders.fixture.test` được trả về đúng **một** địa chỉ IPv4 loopback do provider tạo ra.
- JVM A dùng `-Dfixture.lastOctet=42`, trả về `127.0.0.42` và báo `PASS`.
- JVM B dùng `-Dfixture.lastOctet=43`, trả về `127.0.0.43` và báo `PASS`.
- Mỗi báo cáo mang nhãn lần chạy, thời điểm, PID, phiên bản Java, giá trị kỳ vọng, giá trị thực tế và trạng thái.
- Tra cứu hostname fixture không cần mạng ngoài; các hostname khác được ủy quyền cho resolver mặc định của JDK.

Chọn `.test` vì đây là miền dành cho mục đích kiểm thử; chọn `127.0.0.0/8` để kết quả là địa chỉ loopback, không nhầm với một dịch vụ thực trên Internet. Bài chỉ **phân giải tên thành địa chỉ**; không mở kết nối tới cổng mạng nào.

## 2. Thiết kế fixture và tiêu chí xác nhận

| Thành phần | Giá trị của bài thực hành |
| --- | --- |
| SPI | `java.net.spi.InetAddressResolverProvider` |
| Resolver | `java.net.spi.InetAddressResolver` |
| Tên fixture | `orders.fixture.test` |
| Địa chỉ được tạo | `127.0.0.<octet>` |
| Thuộc tính đầu vào mỗi JVM | `fixture.lastOctet` (`1`–`254`, mặc định `42`) |
| Điểm kiểm thử | `InetAddress.getAllByName("orders.fixture.test")` |
| Tiêu chí PASS | Danh sách trả về chỉ gồm một địa chỉ đúng bằng giá trị kỳ vọng |

Việc chọn IPv4 giúp phép thử nhỏ và dễ đọc. Trong ví dụ, provider xử lý fixture khi chính sách tra cứu cho phép IPv4; nếu yêu cầu chỉ có IPv6, fixture sẽ trả `UnknownHostException`. Đây là hành vi có chủ đích, không tự trả một địa chỉ sai họ.

## 3. Tổ chức mã nguồn bằng module Java

Tạo thư mục dự án theo cấu trúc:

```text
fixture-resolver-demo/
  src/
    module-info.java
    demo/
      fixture/
        FixtureResolverProvider.java
        FixtureProbe.java
```

Bài dùng JPMS để đăng ký chính xác một provider. Nội dung `src/module-info.java`:

```java
module demo.fixture {
    provides java.net.spi.InetAddressResolverProvider
        with demo.fixture.FixtureResolverProvider;
}
```

`provides ... with ...` là khai báo dịch vụ công khai của Java. Khi chạy module này, bạn không cần tệp `META-INF/services`. Nếu chọn cách triển khai trên classpath, đăng ký tên lớp provider qua `META-INF/services/java.net.spi.InetAddressResolverProvider`, đồng thời bảo đảm chỉ một provider mong muốn tồn tại trong bản triển khai.

## 4. Viết provider ánh xạ fixture

Tạo `src/demo/fixture/FixtureResolverProvider.java`:

```java
package demo.fixture;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.Arrays;
import java.util.stream.Stream;

public final class FixtureResolverProvider
        extends InetAddressResolverProvider {

    private static final String FIXTURE_HOST = "orders.fixture.test";

    @Override
    public String name() {
        return "fixture-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        InetAddressResolver builtin = configuration.builtinResolver();

        String raw = System.getProperty("fixture.lastOctet", "42");
        final int octet;
        try {
            octet = Integer.parseInt(raw);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "fixture.lastOctet must be an integer: " + raw, ex);
        }
        if (octet < 1 || octet > 254) {
            throw new IllegalArgumentException(
                    "fixture.lastOctet must be in [1, 254]");
        }

        byte[] fixtureBytes = {127, 0, 0, (byte) octet};
        System.err.printf(
                "[provider] pid=%d name=%s fixture=%s ip=127.0.0.%d%n",
                ProcessHandle.current().pid(), name(), FIXTURE_HOST, octet);

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, LookupPolicy policy)
                    throws UnknownHostException {
                if (!FIXTURE_HOST.equalsIgnoreCase(host)) {
                    return builtin.lookupByName(host, policy);
                }

                if ((policy.characteristics() & LookupPolicy.IPV4) == 0) {
                    throw new UnknownHostException(
                            "IPv4-only fixture: " + host);
                }

                System.err.printf(
                        "[resolver] pid=%d host=%s mapping=127.0.0.%d%n",
                        ProcessHandle.current().pid(), host, octet);

                // Tạo địa chỉ trực tiếp từ byte, không gọi DNS lại.
                return Stream.of(InetAddress.getByAddress(host, fixtureBytes));
            }

            @Override
            public String lookupByAddress(byte[] address)
                    throws UnknownHostException {
                if (Arrays.equals(address, fixtureBytes)) {
                    return FIXTURE_HOST;
                }
                return builtin.lookupByAddress(address);
            }
        };
    }
}
```

**Điểm cần hiểu trong mã:**

1. `get(Configuration)` nhận resolver tích hợp qua `configuration.builtinResolver()`, sau đó đọc cấu hình cho lần khởi tạo này.
2. `lookupByName(...)` chỉ xử lý chính xác hostname fixture (không phân biệt hoa/thường). Hostname khác được chuyển cho resolver tích hợp với nguyên `LookupPolicy`.
3. `LookupPolicy.IPV4` và `policy.characteristics()` giúp không trả địa chỉ IPv4 khi người gọi yêu cầu họ địa chỉ không chứa IPv4. Vì fixture chỉ cung cấp một IPv4, thứ tự IPv4/IPv6 không ảnh hưởng đến kết quả của ca kiểm thử này.
4. `InetAddress.getByAddress(host, fixtureBytes)` chỉ tạo một đối tượng địa chỉ từ byte đã biết, **không yêu cầu phân giải DNS** và không gọi vòng lại `InetAddress.getAllByName(...)`.
5. `lookupByAddress(...)` có một quy tắc ánh xạ ngược phù hợp với fixture; các địa chỉ khác vẫn dùng resolver tích hợp.

Không gọi `InetAddress.getByName(host)` hoặc `InetAddress.getAllByName(host)` bên trong `lookupByName(...)` để tạo fixture: lời gọi như vậy có thể quay lại chính resolver đang thực thi. Với hostname khác fixture, cách ủy quyền đúng là `builtin.lookupByName(host, policy)`.

## 5. Viết chương trình đo và báo cáo

Tạo `src/demo/fixture/FixtureProbe.java`:

```java
package demo.fixture;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.time.Instant;
import java.util.Arrays;
import java.util.stream.Collectors;

public final class FixtureProbe {
    private static final String HOST = "orders.fixture.test";

    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println("Usage: FixtureProbe RUN_ID EXPECTED_OCTET");
            System.exit(64);
            return;
        }

        String runId = args[0];
        String expected = "127.0.0." + args[1];
        String actual;

        try {
            InetAddress[] addresses = InetAddress.getAllByName(HOST);
            actual = Arrays.stream(addresses)
                    .map(InetAddress::getHostAddress)
                    .collect(Collectors.joining(","));
        } catch (UnknownHostException ex) {
            actual = "UNRESOLVED";
        }

        boolean passed = expected.equals(actual);
        System.out.printf(
                "run=%s time=%s pid=%d java=%s host=%s "
                + "expected=%s actual=%s status=%s%n",
                runId, Instant.now(), ProcessHandle.current().pid(),
                Runtime.version(), HOST, expected, actual,
                passed ? "PASS" : "FAIL");

        if (!passed) {
            System.exit(1);
        }
    }
}
```

Báo cáo coi việc trả về nhiều địa chỉ là thất bại, bởi chuỗi `actual` lúc đó chứa nhiều giá trị phân tách bằng dấu phẩy. Mã thoát `0` biểu thị PASS; mã `1` biểu thị FAIL do sai kết quả hoặc không phân giải được. `run` là nhãn do người chạy đặt; `pid` giúp quan sát tiến trình thực thi, còn `time` cho biết thời điểm ghi nhận.

## 6. Biên dịch và chạy bằng hai JVM riêng

Yêu cầu một **JDK 18 trở lên** với `javac` và `java` sẵn trên đường dẫn lệnh. Từ thư mục `fixture-resolver-demo`, tạo thư mục đầu ra:

```bash
# Linux/macOS
mkdir -p mods/demo.fixture
```

Hoặc với Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force mods/demo.fixture | Out-Null
```

Lệnh biên dịch và chạy bên dưới dùng dấu `/` trong đường dẫn nên dùng được với Java trên cả hai môi trường:

```bash
javac -d mods/demo.fixture src/module-info.java src/demo/fixture/FixtureResolverProvider.java src/demo/fixture/FixtureProbe.java

# JVM A
java -Dfixture.lastOctet=42 --module-path mods -m demo.fixture/demo.fixture.FixtureProbe A 42

# JVM B (lệnh java mới, tiến trình JVM mới)
java -Dfixture.lastOctet=43 --module-path mods -m demo.fixture/demo.fixture.FixtureProbe B 43
```

Trên một số terminal, trình thông dịch shell có quy tắc trích dẫn khác nhau; các lệnh ở đây không yêu cầu biến shell hoặc ký tự phân cách classpath. Điều quan trọng là chạy **hai lệnh `java` riêng biệt**. Module path trỏ tới `mods`, chứa một module đã biên dịch tên `demo.fixture`.

### 6.1. Minh họa kết quả kỳ vọng

Ví dụ log dưới đây **mang tính minh họa**; PID, thời gian và chuỗi phiên bản Java thực tế sẽ khác:

```text
[provider] pid=<PID_A> name=fixture-resolver fixture=orders.fixture.test ip=127.0.0.42
[resolver] pid=<PID_A> host=orders.fixture.test mapping=127.0.0.42
run=A time=<ISO_8601_A> pid=<PID_A> java=<JDK_VERSION> host=orders.fixture.test expected=127.0.0.42 actual=127.0.0.42 status=PASS

[provider] pid=<PID_B> name=fixture-resolver fixture=orders.fixture.test ip=127.0.0.43
[resolver] pid=<PID_B> host=orders.fixture.test mapping=127.0.0.43
run=B time=<ISO_8601_B> pid=<PID_B> java=<JDK_VERSION> host=orders.fixture.test expected=127.0.0.43 actual=127.0.0.43 status=PASS
```

| Lần chạy | Thuộc tính JVM | Kết quả cần quan sát | Kỳ vọng |
| --- | --- | --- | --- |
| A | `fixture.lastOctet=42` | `actual=127.0.0.42` | `status=PASS` |
| B | `fixture.lastOctet=43` | `actual=127.0.0.43` | `status=PASS` |

Không tự gán một PID hoặc một thời gian cố định khi lưu báo cáo. Hệ điều hành có thể tái sử dụng PID sau khi một tiến trình kết thúc; bằng chứng về hai JVM riêng là **hai lần khởi động `java` độc lập**, kèm nhãn chạy và log tương ứng. Khi gửi kết quả cho người khác, lưu đủ lệnh, stdout, stderr và mã thoát của từng lần chạy.

### 6.2. Thử nghiệm âm để chứng minh phép đo có thể phát hiện sai

Sau hai lần PASS, thử chạy JVM mới với cấu hình provider và kỳ vọng không trùng nhau:

```bash
java -Dfixture.lastOctet=43 --module-path mods -m demo.fixture/demo.fixture.FixtureProbe C 42
```

Phép thử này được dự kiến có `actual=127.0.0.43`, `expected=127.0.0.42`, `status=FAIL` và mã thoát `1`. Nhờ đó, báo cáo thể hiện được cả trường hợp kết quả sai, thay vì chỉ in dữ liệu mà luôn báo thành công. Đây vẫn là phép thử cục bộ, không cần DNS bên ngoài.

## 7. Giải thích vì sao phải kiểm chứng theo từng JVM

`InetAddress` có cơ chế chọn resolver khi khởi tạo và có thể cache kết quả phân giải tên. Vì vậy, đổi thuộc tính hệ thống hoặc chỉnh module path **sau khi ứng dụng đã bắt đầu sử dụng resolver** không phải cách đáng tin cậy để xác minh provider hay fixture mới được áp dụng.

Luồng thực hành:

```text
JVM A: -Dfixture.lastOctet=42
  -> InetAddress -> FixtureResolverProvider
  -> lookupByName("orders.fixture.test")
  -> 127.0.0.42 -> báo cáo A

JVM B: -Dfixture.lastOctet=43
  -> InetAddress -> FixtureResolverProvider
  -> lookupByName("orders.fixture.test")
  -> 127.0.0.43 -> báo cáo B
```

Mỗi dòng báo cáo được sinh trong một tiến trình độc lập với cấu hình xác định ngay từ lúc khởi động. Nếu muốn đánh giá cache, hãy thiết kế một ca riêng trong cùng JVM và đo nhiều lần gọi; không suy ra rằng một ca không có log `lookupByName` nghĩa là provider không tồn tại.

**Điểm kiểm chứng quan trọng:** log `[provider]` cho biết provider đã tạo resolver, log `[resolver]` cho biết lần tra cứu đã đi vào nhánh fixture, còn `actual` cùng mã thoát xác nhận kết quả mà ứng dụng thật sự nhận được. Kết hợp cả ba hữu ích hơn việc chỉ liệt kê provider qua `ServiceLoader`.

## 8. Xử lý sự cố thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `Module demo.fixture not found` | Chưa biên dịch đúng cấu trúc `mods/demo.fixture` hoặc module path sai | Kiểm tra thư mục output và `--module-path mods` |
| `UnknownHostException: orders.fixture.test` | Provider chưa được đăng ký/chưa được chọn hoặc fixture bị từ chối theo họ địa chỉ | Kiểm tra `module-info.java`, log `[provider]`, cấu hình runtime và `LookupPolicy` |
| Có log provider nhưng không có log tra cứu fixture | Không gọi đúng hostname, có cache hit hoặc luồng thử không đến nhánh fixture | Chạy JVM mới, gọi đúng `orders.fixture.test` và xem stdout/stderr |
| Trả địa chỉ khác kỳ vọng | `-Dfixture.lastOctet` không khớp với đối số kỳ vọng hoặc có provider khác | So sánh lệnh chạy, báo cáo và provider được đóng gói |
| `fixture.lastOctet` ngoài khoảng cho phép | Giá trị không phải số nguyên hoặc ngoài `1`–`254` | Sửa tham số rồi chạy một JVM mới |
| Hai provider cùng đăng ký | Không có cơ chế ưu tiên portable cho SPI này | Thu gọn runtime còn một provider hoặc gộp chiến lược trong một provider điều phối |
| Không phân giải được hostname ngoài fixture | Resolver mặc định cần DNS/mạng của môi trường | Chỉ dùng hostname fixture cho kiểm thử không phụ thuộc mạng |

Một fixture nên dùng dữ liệu riêng và có kỳ vọng chính xác. Đừng chọn `localhost`, tên máy hiện tại hoặc địa chỉ dạng literal như `127.0.0.1` để chứng minh SPI đã được gọi, vì các đường xử lý đặc biệt có thể không đi qua nhánh tra cứu tên giống hostname thông thường.

## 9. Mở rộng sau khi hoàn thành

- Tạo thêm tên `inventory.fixture.test` với địa chỉ loopback khác và bổ sung kiểm thử trả về đúng địa chỉ tương ứng. Mỗi ánh xạ nên được định nghĩa tường minh, tránh `endsWith(".test")` quá rộng.
- Kiểm tra nhánh tra cứu ngược của `lookupByAddress(...)` bằng một bài kiểm thử riêng, lưu ý `InetAddress` có thể cache và có quy trình xác minh tên khi gọi API mức cao.
- Thử chính sách ưu tiên IPv6 và ca chỉ IPv6 trên JDK đang dùng; fixture IPv4 của bài này cần trả `UnknownHostException` khi IPv4 không được chấp nhận.
- Với hệ thống thực tế, chuyển cấu hình fixture ra cơ chế quản lý phù hợp với môi trường và đặt chính sách cụ thể cho cache, fallback, timeout, báo lỗi và bảo mật phân giải tên.

## 10. Câu hỏi tự kiểm tra

1. Vì sao `InetAddress.getByAddress(host, bytes)` là lựa chọn phù hợp khi provider tạo fixture, còn gọi lại `InetAddress.getByName(host)` trong `lookupByName` là rủi ro?
2. Dòng log nào chứng minh provider được khởi tạo, dòng nào chứng minh nhánh fixture được gọi và dữ liệu nào xác nhận ứng dụng nhận đúng địa chỉ?
3. Vì sao hai lần chạy `java` tách biệt đáng tin cậy hơn việc đổi `System.setProperty("fixture.lastOctet", ...)` giữa các lần tra cứu trong cùng JVM?
4. Nếu muốn hỗ trợ cả IPv4 và IPv6, cần xem xét `LookupPolicy` và thứ tự địa chỉ thế nào?
5. Khi nhận `status=FAIL`, cách phân biệt lỗi module path, lỗi đăng ký provider và lỗi kỳ vọng là gì?

**Ghi nhớ:** bài kiểm chứng resolver tốt cần một đầu vào fixture xác định, một provider được đăng ký rõ ràng, phép tra cứu không phụ thuộc DNS bên ngoài và bằng chứng kết quả theo **từng JVM**. Đối chiếu khi nâng cấp JDK với JEP 418, Javadoc của `InetAddressResolverProvider`, `InetAddressResolver` và `InetAddress` trên phiên bản thực tế triển khai.
