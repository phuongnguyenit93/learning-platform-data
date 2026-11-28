# Kiểm thử ma trận IPv4, IPv6, thứ tự ưu tiên và LookupPolicy không hợp lệ

## 1. Mục tiêu kiểm thử

Java 18 giới thiệu **Internet-Address Resolution SPI** theo JEP 418. Trên JDK hiện đại, `InetAddressResolver` nhận một `LookupPolicy` trong mỗi lần tra cứu hostname. Policy mô tả hai nhóm yêu cầu độc lập:

1. **Họ địa chỉ được phép trả về:** IPv4, IPv6 hoặc cả hai.
2. **Thứ tự giữa hai họ:** IPv4 trước, IPv6 trước hoặc thứ tự hệ thống khi không đặt cờ ưu tiên.

Bài này kiểm tra trực tiếp hợp đồng của `InetAddressResolver.lookupByName` bằng một fixture dual-stack cố định. Ta truyền từng policy vào resolver, xác nhận đúng họ IP, đúng thứ tự khi có yêu cầu ưu tiên và đúng ngoại lệ khi policy không hợp lệ.

Không dùng DNS công cộng hay phụ thuộc máy test có IPv6 hoạt động hay không. Tất cả địa chỉ được tạo trực tiếp từ byte fixture; đây là kiểm thử logic phân giải, không phải kiểm tra kết nối mạng.

## 2. Đọc đúng bốn cờ LookupPolicy

`InetAddressResolver.LookupPolicy` có bốn hằng số:

| Cờ | Ý nghĩa |
| --- | --- |
| `IPV4` | Yêu cầu resolver tra cứu và có thể trả địa chỉ IPv4 |
| `IPV6` | Yêu cầu resolver tra cứu và có thể trả địa chỉ IPv6 |
| `IPV4_FIRST` | Khi trả cả hai họ, đặt IPv4 trước IPv6 |
| `IPV6_FIRST` | Khi trả cả hai họ, đặt IPv6 trước IPv4 |

Hai cờ họ địa chỉ và hai cờ thứ tự là hai nhóm khác nhau. Cờ thứ tự **không tự thêm** họ địa chỉ vào kết quả. Ví dụ `IPV4 | IPV6_FIRST` vẫn chỉ yêu cầu IPv4; nếu resolver có IPv4 thì trả IPv4, không tự tìm IPv6.

### Quy tắc hợp lệ của LookupPolicy.of

Factory `LookupPolicy.of(int characteristics)` tạo policy từ bit mask. Theo Javadoc hiện hành:

- Phải có ít nhất một trong `IPV4` hoặc `IPV6`.
- Có thể đặt cả hai cờ họ để yêu cầu cả IPv4 và IPv6.
- Có thể đặt `IPV4_FIRST` hoặc `IPV6_FIRST` để chọn họ được trả trước.
- Nếu không đặt cờ thứ tự nào, policy yêu cầu thứ tự hệ thống.
- Không được đặt đồng thời `IPV4_FIRST` và `IPV6_FIRST`.
- Vi phạm các điều kiện trên làm `LookupPolicy.of` ném `IllegalArgumentException`.

Bảng ví dụ:

| Bit mask | Hợp lệ? | Diễn giải |
| --- | --- | --- |
| `IPV4` | Có | Chỉ IPv4 |
| `IPV6` | Có | Chỉ IPv6 |
| `IPV4` \| `IPV6` | Có | Cả hai họ, thứ tự hệ thống |
| `IPV4` \| `IPV6` \| `IPV4_FIRST` | Có | Cả hai họ, IPv4 trước |
| `IPV4` \| `IPV6` \| `IPV6_FIRST` | Có | Cả hai họ, IPv6 trước |
| `IPV4` \| `IPV6_FIRST` | Có | Chỉ IPv4; cờ IPv6_FIRST không thêm IPv6 |
| `0` | Không | Không chọn họ địa chỉ |
| `IPV4_FIRST` | Không | Có cờ thứ tự nhưng không chọn họ |
| `IPV4` \| `IPV4_FIRST` \| `IPV6_FIRST` | Không | Yêu cầu đồng thời hai thứ tự ưu tiên |
| `IPV4` \| `IPV6` \| `IPV4_FIRST` \| `IPV6_FIRST` | Không | Hai cờ ưu tiên xung đột |

Cần phân biệt hai thời điểm lỗi:

- `LookupPolicy.of(...)` kiểm tra bit mask và từ chối tổ hợp không hợp lệ **ngay khi tạo policy**.
- `lookupByName(...)` nhận một policy hợp lệ, sau đó áp dụng nó để lọc và sắp xếp kết quả. Resolver không cần tự kiểm tra lại những tổ hợp mà factory đã loại bỏ.

## 3. Fixture dual-stack xác định

Sử dụng các hostname dành riêng cho kiểm thử:

| Hostname | IPv4 | IPv6 |
| --- | --- | --- |
| `dual.qa.invalid` | `192.0.2.70` | `2001:db8::70` |
| `v4-only.qa.invalid` | `192.0.2.80` | Không có |
| `v6-only.qa.invalid` | Không có | `2001:db8::80` |
| `missing.qa.invalid` | Không có | Không có |

`.invalid` là miền dành riêng; `192.0.2.0/24` là dải IPv4 dành cho tài liệu; `2001:db8::/32` là dải IPv6 dành cho tài liệu. Các giá trị này không đại diện cho endpoint có thể kết nối.

Trong fixture, nguồn dữ liệu cho `dual.qa.invalid` giữ thứ tự cố định IPv6 rồi IPv4. Đây chỉ là **thứ tự nguồn của fixture** để việc chạy lặp lại ổn định. Khi policy không có cờ `IPV4_FIRST` hoặc `IPV6_FIRST`, test chỉ xác nhận cả hai họ xuất hiện; không khẳng định thứ tự hệ thống trên mọi JDK/máy.

## 4. Cài resolver tôn trọng cả họ IP và thứ tự

Cấu trúc bài tập:

```text
resolver-policy-matrix/
  src/demo/resolver/
    DualStackResolver.java
    LookupPolicyMatrixCheck.java
```

Tạo `src/demo/resolver/DualStackResolver.java`:

```java
package demo.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Stream;

public final class DualStackResolver implements InetAddressResolver {
    private static final String DUAL = "dual.qa.invalid";
    private static final String V4_ONLY = "v4-only.qa.invalid";
    private static final String V6_ONLY = "v6-only.qa.invalid";

    private static final byte[] DUAL_V4 =
            {(byte) 192, 0, 2, 70};
    private static final byte[] V4_ONLY_ADDRESS =
            {(byte) 192, 0, 2, 80};

    private static final byte[] DUAL_V6 = {
        0x20, 0x01, 0x0d, (byte) 0xb8,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x70
    };
    private static final byte[] V6_ONLY_ADDRESS = {
        0x20, 0x01, 0x0d, (byte) 0xb8,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, (byte) 0x80
    };

    // Thứ tự nguồn của fixture dual-stack: IPv6 trước IPv4.
    private static final Map<String, List<byte[]>> RECORDS = Map.of(
            DUAL, List.of(DUAL_V6, DUAL_V4),
            V4_ONLY, List.of(V4_ONLY_ADDRESS),
            V6_ONLY, List.of(V6_ONLY_ADDRESS)
    );

    @Override
    public Stream<InetAddress> lookupByName(String host, LookupPolicy policy)
            throws UnknownHostException {
        Objects.requireNonNull(host, "host");
        Objects.requireNonNull(policy, "policy");

        int flags = policy.characteristics();
        boolean wantsV4 = (flags & LookupPolicy.IPV4) != 0;
        boolean wantsV6 = (flags & LookupPolicy.IPV6) != 0;
        boolean v4First = (flags & LookupPolicy.IPV4_FIRST) != 0;
        boolean v6First = (flags & LookupPolicy.IPV6_FIRST) != 0;

        List<byte[]> record = RECORDS.get(host.toLowerCase(Locale.ROOT));
        if (record == null) {
            throw new UnknownHostException(host);
        }

        List<InetAddress> sourceOrder = new ArrayList<>();
        List<InetAddress> ipv4 = new ArrayList<>();
        List<InetAddress> ipv6 = new ArrayList<>();

        for (byte[] rawAddress : record) {
            boolean isV4 = rawAddress.length == 4;
            boolean isV6 = rawAddress.length == 16;

            if ((isV4 && wantsV4) || (isV6 && wantsV6)) {
                InetAddress address = InetAddress.getByAddress(host, rawAddress);
                sourceOrder.add(address);
                if (isV4) {
                    ipv4.add(address);
                } else {
                    ipv6.add(address);
                }
            }
        }

        if (sourceOrder.isEmpty()) {
            throw new UnknownHostException(
                    host + " không có họ IP được yêu cầu");
        }

        if (v4First) {
            ipv4.addAll(ipv6);
            return ipv4.stream();
        }

        if (v6First) {
            ipv6.addAll(ipv4);
            return ipv6.stream();
        }

        // Không có cờ ưu tiên: giữ thứ tự từ nguồn dữ liệu của resolver.
        return sourceOrder.stream();
    }

    @Override
    public String lookupByAddress(byte[] address)
            throws UnknownHostException {
        Objects.requireNonNull(address, "address");
        if (address.length != 4 && address.length != 16) {
            throw new IllegalArgumentException("IP cần 4 hoặc 16 byte");
        }

        for (var entry : RECORDS.entrySet()) {
            for (byte[] raw : entry.getValue()) {
                if (Arrays.equals(address, raw)) {
                    return entry.getKey();
                }
            }
        }
        throw new UnknownHostException("IP không có trong fixture");
    }
}
```

### Vì sao resolver tách ba danh sách?

- `sourceOrder` giữ thứ tự vốn có từ nguồn dữ liệu. Khi không có cờ ưu tiên, resolver trả danh sách này.
- `ipv4` chỉ chứa địa chỉ IPv4 được policy cho phép.
- `ipv6` chỉ chứa địa chỉ IPv6 được policy cho phép.

Nếu policy yêu cầu IPv4 trước, resolver ghép IPv4 rồi IPv6. Nếu yêu cầu IPv6 trước, resolver ghép IPv6 rồi IPv4. Nếu chỉ yêu cầu một họ, danh sách họ còn lại rỗng và kết quả chỉ chứa họ được chọn.

`InetAddress.getByAddress(host, rawAddress)` tạo địa chỉ từ byte có sẵn, không gọi phân giải DNS. Điều này tránh lookup lồng nhau trong resolver và làm fixture độc lập mạng.

## 5. Chương trình kiểm thử ma trận

Tạo `src/demo/resolver/LookupPolicyMatrixCheck.java`:

```java
package demo.resolver;

import java.net.Inet4Address;
import java.net.Inet6Address;
import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.util.Arrays;
import java.util.List;

public final class LookupPolicyMatrixCheck {
    private static final String DUAL = "dual.qa.invalid";
    private static final byte[] DUAL_V4 =
            {(byte) 192, 0, 2, 70};
    private static final byte[] DUAL_V6 = {
        0x20, 0x01, 0x0d, (byte) 0xb8,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x70
    };

    @FunctionalInterface
    private interface CheckedLookup {
        void run() throws UnknownHostException;
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    private static List<InetAddress> lookup(
            DualStackResolver resolver, String host, int flags)
            throws UnknownHostException {
        LookupPolicy policy = LookupPolicy.of(flags);
        require(policy.characteristics() == flags,
                "characteristics() phải trả lại đúng bit mask");
        return resolver.lookupByName(host, policy).toList();
    }

    private static void expectUnknown(CheckedLookup operation) {
        try {
            operation.run();
            throw new AssertionError("Phải ném UnknownHostException");
        } catch (UnknownHostException expected) {
            // Kết quả mong đợi.
        }
    }

    private static void expectNullPointer(CheckedLookup operation) {
        try {
            operation.run();
            throw new AssertionError("Phải ném NullPointerException");
        } catch (NullPointerException expected) {
            // Kết quả mong đợi.
        }
    }

    private static void expectInvalidPolicy(int flags, String label) {
        try {
            LookupPolicy.of(flags);
            throw new AssertionError(
                    "LookupPolicy.of phải từ chối: " + label);
        } catch (IllegalArgumentException expected) {
            // Kết quả mong đợi.
        }
    }

    private static void assertBothFamilies(List<InetAddress> addresses) {
        require(addresses.size() == 2,
                "Dual-stack phải có đúng hai địa chỉ: " + addresses);

        long v4Count = addresses.stream()
                .filter(Inet4Address.class::isInstance).count();
        long v6Count = addresses.stream()
                .filter(Inet6Address.class::isInstance).count();

        require(v4Count == 1 && v6Count == 1,
                "Phải có một IPv4 và một IPv6: " + addresses);
    }

    private static void assertOrder(
            List<InetAddress> addresses, boolean ipv4First) {
        assertBothFamilies(addresses);
        if (ipv4First) {
            require(addresses.get(0) instanceof Inet4Address,
                    "IPv4 phải đứng trước");
            require(addresses.get(1) instanceof Inet6Address,
                    "IPv6 phải đứng sau");
        } else {
            require(addresses.get(0) instanceof Inet6Address,
                    "IPv6 phải đứng trước");
            require(addresses.get(1) instanceof Inet4Address,
                    "IPv4 phải đứng sau");
        }
    }

    private static void assertSingleAddress(
            List<InetAddress> addresses, Class<?> family, byte[] expected) {
        require(addresses.size() == 1,
                "Cần đúng một địa chỉ: " + addresses);
        require(family.isInstance(addresses.get(0)),
                "Sai họ địa chỉ: " + addresses.get(0).getClass());
        require(Arrays.equals(expected, addresses.get(0).getAddress()),
                "Sai byte IP: " + addresses.get(0).getHostAddress());
    }

    public static void main(String[] args) throws Exception {
        DualStackResolver resolver = new DualStackResolver();

        // A. Chỉ yêu cầu IPv4.
        var ipv4 = lookup(resolver, DUAL, LookupPolicy.IPV4);
        assertSingleAddress(ipv4, Inet4Address.class, DUAL_V4);

        // B. Chỉ yêu cầu IPv6.
        var ipv6 = lookup(resolver, DUAL, LookupPolicy.IPV6);
        assertSingleAddress(ipv6, Inet6Address.class, DUAL_V6);

        // C. Yêu cầu cả hai, không ép thứ tự.
        var systemOrder = lookup(
                resolver, DUAL, LookupPolicy.IPV4 | LookupPolicy.IPV6);
        assertBothFamilies(systemOrder);
        // Không assert phần tử đầu: system order phụ thuộc nguồn/triển khai.

        // D. Ép IPv4 đứng trước IPv6.
        var v4First = lookup(resolver, DUAL,
                LookupPolicy.IPV4 | LookupPolicy.IPV6
                        | LookupPolicy.IPV4_FIRST);
        assertOrder(v4First, true);

        // E. Ép IPv6 đứng trước IPv4.
        var v6First = lookup(resolver, DUAL,
                LookupPolicy.IPV4 | LookupPolicy.IPV6
                        | LookupPolicy.IPV6_FIRST);
        assertOrder(v6First, false);

        // F. Cờ thứ tự không tự thêm họ địa chỉ bị loại.
        var v4OnlyV6First = lookup(resolver, DUAL,
                LookupPolicy.IPV4 | LookupPolicy.IPV6_FIRST);
        assertSingleAddress(v4OnlyV6First, Inet4Address.class, DUAL_V4);

        // G. Host chỉ có IPv4 nhưng policy yêu cầu IPv6.
        expectUnknown(() -> resolver.lookupByName(
                "v4-only.qa.invalid",
                LookupPolicy.of(LookupPolicy.IPV6)));

        // H. Host chỉ có IPv6 nhưng policy yêu cầu IPv4.
        expectUnknown(() -> resolver.lookupByName(
                "v6-only.qa.invalid",
                LookupPolicy.of(LookupPolicy.IPV4)));

        // I. Hostname không có trong fixture.
        expectUnknown(() -> resolver.lookupByName(
                "missing.qa.invalid",
                LookupPolicy.of(LookupPolicy.IPV4 | LookupPolicy.IPV6)));

        // J. LookupPolicy.of phải từ chối bit mask không hợp lệ.
        expectInvalidPolicy(0, "không chọn IPV4 hoặc IPV6");
        expectInvalidPolicy(LookupPolicy.IPV4_FIRST,
                "chỉ có cờ ưu tiên, không có họ địa chỉ");
        expectInvalidPolicy(
                LookupPolicy.IPV4 | LookupPolicy.IPV6
                        | LookupPolicy.IPV4_FIRST | LookupPolicy.IPV6_FIRST,
                "đặt đồng thời IPV4_FIRST và IPV6_FIRST");

        // K. Hợp đồng null của lookupByName.
        expectNullPointer(() -> resolver.lookupByName(
                null, LookupPolicy.of(LookupPolicy.IPV4)));
        expectNullPointer(() -> resolver.lookupByName(
                DUAL, null));

        System.out.println("PASS: IPV4 only");
        System.out.println("PASS: IPV6 only");
        System.out.println("PASS: both families without forced order");
        System.out.println("PASS: IPV4_FIRST");
        System.out.println("PASS: IPV6_FIRST");
        System.out.println("PASS: priority flag does not add an address family");
        System.out.println("PASS: unavailable family and unknown host");
        System.out.println("PASS: invalid LookupPolicy masks");
        System.out.println("PASS: null host and policy");
    }
}
```

### Vì sao test thứ tự hệ thống không so sánh phần tử đầu?

Policy `IPV4 | IPV6` không chứa `IPV4_FIRST` hay `IPV6_FIRST`. Theo Javadoc, đó là thứ tự hệ thống. Thứ tự tự nhiên có thể phụ thuộc resolver nền, hệ điều hành và cấu hình. Fixture có thứ tự nguồn IPv6 rồi IPv4 để tái lập, nhưng test chỉ yêu cầu đủ hai họ. Hai policy có cờ ưu tiên mới có assertion thứ tự cụ thể.

## 6. Ma trận kỳ vọng và cách đọc kết quả

| Ca | Policy | Kết quả bắt buộc |
| --- | --- | --- |
| A | `IPV4` | Một IPv4 |
| B | `IPV6` | Một IPv6 |
| C | `IPV4` \| `IPV6` | Có một IPv4 và một IPv6; không áp đặt thứ tự |
| D | `IPV4` \| `IPV6` \| `IPV4_FIRST` | IPv4 đứng trước IPv6 |
| E | `IPV4` \| `IPV6` \| `IPV6_FIRST` | IPv6 đứng trước IPv4 |
| F | `IPV4` \| `IPV6_FIRST` | Chỉ IPv4; cờ ưu tiên không mở rộng họ địa chỉ |
| G | `IPV6` trên hostname chỉ có IPv4 | `UnknownHostException` |
| H | `IPV4` trên hostname chỉ có IPv6 | `UnknownHostException` |
| I | Bất kỳ policy hợp lệ trên hostname không tồn tại | `UnknownHostException` |
| J | Mask không có họ hoặc hai cờ thứ tự | `IllegalArgumentException` tại `LookupPolicy.of` |
| K | Host hoặc policy là `null` | `NullPointerException` tại resolver |

Các ca A–F kiểm tra việc resolver áp dụng policy hợp lệ. Các ca G–I kiểm tra không trả sai họ địa chỉ hoặc dữ liệu không tồn tại. Ca J kiểm tra hợp đồng của factory JDK, còn ca K kiểm tra hợp đồng null của `lookupByName`.

### Kết quả kỳ vọng khi chạy

```text
PASS: IPV4 only
PASS: IPV6 only
PASS: both families without forced order
PASS: IPV4_FIRST
PASS: IPV6_FIRST
PASS: priority flag does not add an address family
PASS: unavailable family and unknown host
PASS: invalid LookupPolicy masks
PASS: null host and policy
```

Nếu một ca thất bại, đọc thông báo `AssertionError` để phân biệt sai họ, sai byte IP, sai thứ tự hay thiếu ngoại lệ. Một test chỉ kiểm tra số lượng phần tử là chưa đủ: resolver có thể trả hai địa chỉ IPv4 và vẫn đạt size 2. Bài này kiểm cả kiểu runtime `Inet4Address`/`Inet6Address` và byte IP.

## 7. Biên dịch và chạy trên JDK 18+

Đây là contract test trực tiếp, không cần service descriptor hay provider JAR. Test tạo `DualStackResolver` bằng `new` và truyền policy cụ thể vào `lookupByName`. Nhờ vậy mỗi ca kiểm soát chính xác bit mask và không bị system-wide resolver của JVM thay đổi kết quả.

Từ thư mục `resolver-policy-matrix`, chạy trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path out | Out-Null
javac --release 18 -d out src/demo/resolver/DualStackResolver.java src/demo/resolver/LookupPolicyMatrixCheck.java
java -cp out demo.resolver.LookupPolicyMatrixCheck
```

Trên Bash/Linux/macOS:

```bash
mkdir -p out
javac --release 18 -d out src/demo/resolver/DualStackResolver.java src/demo/resolver/LookupPolicyMatrixCheck.java
java -cp out demo.resolver.LookupPolicyMatrixCheck
```

Kết quả kỳ vọng:

```text
PASS: IPV4 only
PASS: IPV6 only
PASS: both families without forced order
PASS: IPV4_FIRST
PASS: IPV6_FIRST
PASS: priority flag does not add an address family
PASS: unavailable family and unknown host
PASS: invalid LookupPolicy masks
PASS: null host and policy
```

`--release 18` giúp xác nhận ví dụ chỉ dùng API có từ Java 18 trở xuống. `LookupPolicy` là API công khai trong `java.net.spi`; không cần mở module nội bộ, reflection hoặc tùy chọn JVM đặc biệt.

## 8. Vì sao nên test trực tiếp trước khi test qua InetAddress?

`InetAddress.getAllByName(host)` không nhận đối số `LookupPolicy`. JVM xây dựng policy nền tảng bằng các system properties liên quan đến IPv4/IPv6 và truyền policy đó cho resolver đã cài. Vì vậy, nếu chỉ gọi `InetAddress.getAllByName` trong một test, ta không chủ động ép từng tổ hợp bit mask như ở ma trận trên.

Hai lớp test có mục đích khác nhau:

| Phạm vi | Cách gọi | Điều được chứng minh |
| --- | --- | --- |
| Contract/unit test | `resolver.lookupByName(host, LookupPolicy.of(flags))` | Resolver lọc họ IP và sắp xếp đúng với policy được truyền |
| SPI integration test | `InetAddress.getAllByName(host)` trong JVM mới | Provider được cài và JVM sử dụng policy nền tảng khi phân giải |

Trong một integration suite riêng, có thể chạy mỗi cấu hình system property trong một JVM con mới, vì platform lookup policy được khởi tạo khi `InetAddress` được khởi tạo. Các thuộc tính cần nghiên cứu gồm:

- `java.net.preferIPv4Stack`: yêu cầu ngăn xếp IPv4-only khi đặt `true`; ảnh hưởng khả năng dùng IPv6.
- `java.net.preferIPv6Addresses`: `true` ưu tiên IPv6, `false` ưu tiên IPv4, `system` giữ thứ tự địa chỉ do hệ thống trả về theo tài liệu networking properties.

Đặt property trước khi JVM khởi động, ví dụ:

```powershell
java -Djava.net.preferIPv6Addresses=true -cp "app-classes;provider.jar" your.package.InetAddressCheck
```

`your.package.InetAddressCheck` là tên lớp main của integration test trong ứng dụng; lệnh này minh họa cách truyền property trước khi JVM khởi động.

Không thay đổi property sau khi `InetAddress` đã khởi tạo và kỳ vọng policy nền tảng được tính lại. Cũng không khẳng định cùng một policy hệ thống sẽ cho cùng thứ tự trên mọi OS, vì cấu hình stack và nguồn resolver có thể khác nhau.

## 9. Các lỗi triển khai resolver cần tránh

### 9.1. Luôn trả cả IPv4 lẫn IPv6

Sai:

```java
// Sai: bỏ qua họ địa chỉ mà LookupPolicy không yêu cầu.
return Stream.of(ipv4Address, ipv6Address);
```

Nếu policy chỉ có `IPV4`, resolver không được trả thêm IPv6. Hãy kiểm tra từng bit trước khi thêm địa chỉ vào kết quả.

### 9.2. Chỉ lọc họ IP nhưng bỏ qua thứ tự

Một resolver có thể trả đúng hai địa chỉ nhưng vẫn sai hợp đồng nếu policy đặt `IPV6_FIRST` mà IPv4 đứng trước. Test cần xác nhận kiểu của từng phần tử ở vị trí đầu/cuối, không chỉ kiểm tra size hoặc tập hợp.

### 9.3. Xem thứ tự mặc định là IPv4-first

Nếu không có `IPV4_FIRST` hoặc `IPV6_FIRST`, policy yêu cầu thứ tự hệ thống. Không tự suy luận rằng mọi JDK hoặc OS đều phải trả IPv4 trước. Nếu resolver dùng backend có thứ tự riêng, hãy giữ thứ tự nền của backend trong trường hợp không có cờ ưu tiên; fixture của bài cũng không assert thứ tự này.

### 9.4. Nghĩ cờ ưu tiên sẽ bật họ IP tương ứng

`IPV4 | IPV6_FIRST` không phải yêu cầu cả hai họ. Nó yêu cầu IPv4 và đặt IPv6-first nếu có cả hai, nhưng vì IPv6 không được chọn nên kết quả chỉ có IPv4. Cờ họ địa chỉ quyết định lọc; cờ ưu tiên chỉ quyết định thứ tự.

### 9.5. Tự tạo policy không hợp lệ rồi đẩy xuống resolver

`LookupPolicy.of` đã kiểm tra bit mask. Nếu mask thiếu họ hoặc có hai cờ ưu tiên xung đột, factory ném `IllegalArgumentException` và không tạo policy. Unit test nên kiểm tra ngoại lệ ở đúng factory, không mong resolver nhận một đối tượng policy sai cấu trúc.

### 9.6. Nhầm lỗi policy với hostname không có địa chỉ

Hai lỗi xảy ra ở hai bước khác nhau:

- `IllegalArgumentException`: bit mask không hợp lệ, lỗi xảy ra khi gọi `LookupPolicy.of`.
- `UnknownHostException`: policy hợp lệ nhưng resolver không tìm thấy địa chỉ phù hợp cho hostname/họ IP được yêu cầu.

Đừng bắt chung `Exception` cho cả hai; làm vậy có thể che lỗi logic và khiến test PASS sai.

## 10. Checklist và bài tập mở rộng

- [ ] Policy chỉ IPv4 trả đúng một `Inet4Address`.
- [ ] Policy chỉ IPv6 trả đúng một `Inet6Address`.
- [ ] Policy cả hai họ trả đủ một IPv4 và một IPv6.
- [ ] `IPV4_FIRST` đặt IPv4 trước IPv6.
- [ ] `IPV6_FIRST` đặt IPv6 trước IPv4.
- [ ] Không có cờ ưu tiên thì test không áp đặt thứ tự cố định.
- [ ] Cờ ưu tiên không làm xuất hiện họ địa chỉ không được yêu cầu.
- [ ] Host chỉ có một họ nhưng policy yêu cầu họ còn lại phải ném `UnknownHostException`.
- [ ] `LookupPolicy.of(0)` và mask có cả hai cờ ưu tiên ném `IllegalArgumentException`.
- [ ] Host hoặc policy `null` làm resolver ném `NullPointerException`.

**Bài tập:** Thêm hostname `v4-multi.qa.invalid` có hai IPv4 và hostname `v6-multi.qa.invalid` có hai IPv6. Mở rộng fixture để xác nhận resolver giữ nguyên thứ tự nội bộ của cùng một họ, đồng thời vẫn đặt đúng họ trước khi policy yêu cầu cả hai. Thêm ca kiểm tra policy chỉ một họ để bảo đảm địa chỉ của họ kia không lọt vào kết quả.

**Tiêu chí hoàn thành:** Ma trận kiểm thử chứng minh được việc lọc IPv4/IPv6, thứ tự ưu tiên, thứ tự hệ thống khi không ép ưu tiên, ngoại lệ của bit mask không hợp lệ và ngoại lệ khi không có địa chỉ phù hợp. Mã ví dụ chạy độc lập trên JDK 18 trở lên và không phụ thuộc DNS công cộng.

## Tài liệu tham khảo

- [JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418): giới thiệu resolver SPI trong Java 18.
- [Javadoc InetAddressResolver.LookupPolicy – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.LookupPolicy.html): bốn cờ, quy tắc kết hợp bit mask và `IllegalArgumentException`.
- [Javadoc InetAddressResolver – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/spi/InetAddressResolver.html): hợp đồng họ địa chỉ, thứ tự trả về và ngoại lệ của `lookupByName`.
- [Javadoc InetAddress – Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html): API phân giải tên sử dụng resolver cấp JVM.
- [Core Libraries Developer Guide – Java SE 25](https://docs.oracle.com/en/java/javase/25/core/java-core-libraries-developer-guide.pdf): các system properties ảnh hưởng lựa chọn và thứ tự IPv4/IPv6.
- [RFC 2606](https://www.rfc-editor.org/rfc/rfc2606), [RFC 5737](https://www.rfc-editor.org/rfc/rfc5737), [RFC 3849](https://www.rfc-editor.org/rfc/rfc3849): miền và dải IP dành cho tài liệu/kiểm thử.
