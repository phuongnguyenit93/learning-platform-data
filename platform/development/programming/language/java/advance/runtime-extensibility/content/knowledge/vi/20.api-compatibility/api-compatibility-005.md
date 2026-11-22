# Đàm phán khả năng hỗ trợ và từ chối phiên bản hợp đồng không tương thích

## 1. Vì sao nạp được class chưa chắc đã tương thích?

Trong hệ thống Java runtime-extensibility, plugin và host trao đổi qua một **hợp đồng API/SPI**. `ServiceLoader` hoặc classloader có thể phát hiện provider, nhưng việc khởi tạo được class không chứng minh rằng provider hiểu đúng semantics mà host cần. Một plugin có thể biên dịch với bản hợp đồng cũ, thiếu chức năng mới, hiểu khác định dạng dữ liệu hoặc dựa trên behavior đã bị loại bỏ.

Cần phân biệt ba câu hỏi:

1. **Binary compatibility:** bytecode plugin có liên kết với các class/method host đang cung cấp không?
2. **Contract compatibility:** ý nghĩa, invariants, dữ liệu và lifecycle của phiên bản API có còn được tôn trọng không?
3. **Capability compatibility:** plugin cụ thể có hỗ trợ các tính năng bắt buộc cho workload hiện tại không?

Ví dụ: plugin và host cùng biết `PaymentProvider`, nhưng host yêu cầu idempotent refunds và plugin chỉ xử lý thanh toán một chiều. Dù object có kiểu Java hợp lệ, host phải **từ chối plugin cho tác vụ refund**, thay vì chờ lỗi ở production.

## 2. Một hợp đồng đàm phán gồm những thành phần nào?

| Thông tin | Phía cung cấp | Cách kiểm tra |
| --- | --- | --- |
| Contract/API identity | SDK chung và host | Cùng service interface/namespace và class identity |
| Contract major/minor hoặc protocol version | SDK/plugin metadata | Chính sách compatibility đã công bố |
| Supported version range | Plugin hoặc manifest | Host version thuộc miền hỗ trợ |
| Capability set | Provider | Chứa toàn bộ capability bắt buộc |
| Capability semantics | Contract documentation | Định nghĩa rõ điều kiện/đầu ra của từng capability |
| Runtime prerequisites | Plugin metadata | JDK, OS, native dependency, quyền/quotas |
| Optional extensions | Provider | Chỉ gọi khi được xác nhận hỗ trợ |

**Nguyên tắc:** đàm phán phải diễn ra **trước khi kích hoạt provider để nhận request**, tốt nhất trước khi mở nhiều tài nguyên hoặc đăng ký callback. Mọi lỗi ở bước handshake phải dẫn đến reject rõ ràng, không ghi plugin là READY.

## 3. Tách compatibility policy khỏi việc so sánh chuỗi phiên bản

Semantic versioning (SemVer) có thể là một **quy ước phát hành** hữu ích, nhưng JVM không tự áp dụng SemVer cho API và JPMS module version cũng không tự giải quyết mọi tương thích semantic. Một host có thể định nghĩa:

- `major` đổi khi breaking contract: ví dụ loại method, đổi kiểu dữ liệu, đổi semantics bắt buộc.
- `minor` tăng khi thêm capability tùy chọn hoặc behavior tương thích đã được quy định.
- `patch` dùng cho bug fix không phá hợp đồng.

Tuy nhiên không thể kết luận `host.major == plugin.major` là đủ. Cần kiểm tra required features, giới hạn optional behavior, phiên bản nhỏ tối thiểu và binary linkage thực tế. Ngược lại, plugin báo cùng major nhưng không khai báo capability bắt buộc vẫn phải bị từ chối.

Ví dụ chính sách cho một hợp đồng đã công bố:

```text
Host contract: 2.4
Supported provider major: 2
Provider requires host minor <= provider.maxMinorSupported
Host requires capability: BATCH
Optional host capability: AUDIT

Provider A: major=2, supportedMinor=1..5, capabilities=[BATCH] -> ACCEPT
Provider B: major=1, supportedMinor=0..9, capabilities=[BATCH] -> REJECT major
Provider C: major=2, supportedMinor=1..5, capabilities=[] -> REJECT capability
Provider D: major=2, supportedMinor=5..8, capabilities=[BATCH] -> REJECT range
```

Đây là **policy minh họa** chứ không phải quy luật bắt buộc của mọi plugin system. Với các hợp đồng nghiêm ngặt, host và provider có thể dùng exact version hoặc protocol schema hash thay vì một range.

## 4. Thiết kế interface: metadata trước, tác vụ sau

Host nên sở hữu `ProviderDescriptor` và validator ở một module API/host ổn định. Provider có thể khai báo version range và tập capability; host phải kiểm chứng dữ liệu đó, không mặc định tin một chuỗi quảng cáo.

Điều cần tránh:

```java
// Anti-pattern: gọi tính năng mới rồi mới biết plugin không hỗ trợ.
provider.processBatch(input);
```

Đoạn minh họa này không phải chương trình độc lập. Cách tiếp cận đúng là **validate → select → activate → invoke**.

Đàm phán thường là capability discovery ở runtime, không phải thương lượng không giới hạn. Host phải xác định rõ những yêu cầu bắt buộc; provider chỉ khai báo khả năng; quyết định cuối thuộc về host. Các capability nhạy cảm (ví dụ quyền đọc file/mạng) cần kiểm tra quyền thực tế ở OS/runtime, không chỉ metadata tự khai.

## 5. Ví dụ Java 17+ hoàn chỉnh: host chấp nhận/từ chối provider

Ví dụ dùng một service contract đơn giản. Tất cả nằm trong một file để chạy độc lập, nhưng khi triển khai plugin thật hãy tách SPI vào module API, provider vào JAR riêng và host phụ trách negotiation.

Tạo file `CapabilityNegotiationDemo.java`:

```java
import java.util.EnumSet;
import java.util.List;
import java.util.Set;

public class CapabilityNegotiationDemo {
    enum Capability { BATCH, AUDIT }

    record Contract(int major, int minor) {
        Contract {
            if (major < 0 || minor < 0) {
                throw new IllegalArgumentException("Invalid contract version");
            }
        }
    }

    record Descriptor(int major, int minMinor, int maxMinor,
                      Set<Capability> capabilities) {
        Descriptor {
            if (major < 0 || minMinor < 0 || maxMinor < minMinor) {
                throw new IllegalArgumentException("Invalid version range");
            }
            capabilities = Set.copyOf(capabilities);
        }
    }

    interface Provider {
        String name();
        Descriptor descriptor();
        String executeBatch();
    }

    record Candidate(String name, Descriptor descriptor)
            implements Provider {
        @Override
        public String executeBatch() {
            return "processed by " + name;
        }
    }

    static String rejection(Contract host,
                            Set<Capability> required, Descriptor d) {
        if (host.major() != d.major()) {
            return "unsupported contract major";
        }
        if (host.minor() < d.minMinor() || host.minor() > d.maxMinor()) {
            return "unsupported contract minor";
        }
        if (!d.capabilities().containsAll(required)) {
            return "missing required capability";
        }
        return null;
    }

    public static void main(String[] args) {
        Contract host = new Contract(2, 4);
        Set<Capability> required = EnumSet.of(Capability.BATCH);
        List<Provider> providers = List.of(
            new Candidate("A", new Descriptor(2, 1, 5,
                EnumSet.of(Capability.BATCH))),
            new Candidate("B", new Descriptor(1, 0, 9,
                EnumSet.of(Capability.BATCH))),
            new Candidate("C", new Descriptor(2, 1, 5,
                EnumSet.noneOf(Capability.class))),
            new Candidate("D", new Descriptor(2, 5, 8,
                EnumSet.of(Capability.BATCH)))
        );

        for (Provider provider : providers) {
            String reason = rejection(host, required, provider.descriptor());
            if (reason != null) {
                System.out.println(provider.name() + ": REJECT - " + reason);
                continue;
            }
            System.out.println(provider.name() + ": ACCEPT - "
                + provider.executeBatch());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 CapabilityNegotiationDemo.java
java CapabilityNegotiationDemo
```

Output:

```text
A: ACCEPT - processed by A
B: REJECT - unsupported contract major
C: REJECT - missing required capability
D: REJECT - unsupported contract minor
```

Ví dụ chứng minh rằng **provider được nhìn thấy** không đồng nghĩa **được chọn**. Host xét version range và capabilities trước, rồi mới gọi `executeBatch()` của provider A. Trong ứng dụng thực tế, phải bảo đảm phần metadata/handshake dùng API chung đã tương thích; nếu chữ ký interface handshake bị phá, plugin có thể thất bại khi linkage trước khi kịp tự báo version.

## 6. Gắn negotiation vào ServiceLoader hoặc registry plugin

Với service provider nạp bằng SPI, thứ tự xử lý nên như sau:

```text
Discover candidates
   |
Check artifact descriptor / supported API
   |
Resolve/load using compatible classloader or ModuleLayer
   |
Read provider descriptor
   |
Validate version range + required capabilities
   |
Reject with reason OR activate
   |
Route requests only to accepted providers
```

Đoạn code minh họa (bên trong method có `ServiceLoader<Provider> loader`, `Contract host` và `Set<Capability> required`):

```java
for (Provider provider : loader) {
    Descriptor metadata = provider.descriptor();
    String reason = rejection(host, required, metadata);
    if (reason != null) {
        logRejected(provider.name(), reason);
        continue;
    }
    registerAccepted(provider);
}
```

Trong đoạn này, `logRejected` và `registerAccepted` là hàm ứng dụng tự định nghĩa. `ServiceLoader` có thể tạo provider instance khi iterator được duyệt; nếu constructor/provider initialization đã có side effect, chỉ kiểm tra `descriptor()` là chưa đủ an toàn. Plugin framework nâng cao nên đọc metadata **trước khởi tạo implementation** (manifest/descriptor được ký hoặc kiểm soát), sau đó load provider và xác thực lại.

Đặc biệt khi host và provider được nạp bởi các classloader khác nhau, cả hai phải nhìn thấy **cùng class identity của SPI**. Nạp hai bản interface trùng tên từ child-first loaders không tự động tạo hợp đồng tương thích; có thể gây `ClassCastException`, `ServiceConfigurationError` hoặc lỗi linkage.

## 7. Thương lượng capability có semantics rõ ràng

Capability không chỉ là một nhãn string. Chẳng hạn `BATCH` cần quy định:

- `BATCH` xử lý atomic hay partial success?
- Batch size tối đa, order guarantees và retry policy là gì?
- Lỗi có idempotency key không?
- Version nào đưa capability này vào contract?
- Nếu capability được khai báo nhưng request vượt giới hạn, host cần fallback hay reject?

Nên gắn mỗi capability với schema/contract revision nếu semantics phát triển độc lập, hoặc dùng typed descriptor như `BatchSupport(maxSize, atomic, retrySafe)`. `Set<String>` có thể đủ cho demo, nhưng production cần validation, tránh typo, unknown capability và thay đổi ý nghĩa âm thầm.

**Optional capability:** host chỉ gọi khi provider xác nhận hỗ trợ. **Required capability:** thiếu là lý do reject. Không fallback sang phương án làm mất correctness (ví dụ chuyển thanh toán atomic thành partial) nếu business contract không cho phép.

## 8. Fail-fast và báo lỗi có thể hành động

Đầu ra từ negotiation không nên chỉ là boolean. Cần lý do cụ thể và có cấu trúc:

| Mã từ chối | Ý nghĩa | Hành động vận hành |
| --- | --- | --- |
| `API_MAJOR_MISMATCH` | Không cùng major được hỗ trợ | Nâng cấp/hạ cấp SDK hoặc provider |
| `API_MINOR_OUT_OF_RANGE` | Host nằm ngoài range plugin hỗ trợ | Xác định dải version phù hợp |
| `MISSING_CAPABILITY` | Không có tính năng bắt buộc | Cài provider phù hợp hoặc đổi yêu cầu |
| `INVALID_DESCRIPTOR` | Metadata rỗng/sai/không nhất quán | Sửa artifact plugin |
| `BINARY_INCOMPATIBLE` | Linkage/API signature không phù hợp | Kiểm tra JAR, SDK version, classloader |
| `RUNTIME_UNSUPPORTED` | JDK/OS/native dependency không đáp ứng | Chọn runtime phù hợp |

Host nên log plugin ID, artifact version, host contract, supported range, required vs advertised capabilities và reason code. Tránh đổ stacktrace dài cho mọi trường hợp version không tương thích đã biết; chỉ giữ stacktrace khi có lỗi bất thường. Không expose path hoặc secrets qua message gửi người dùng cuối.

## 9. Thời điểm nào phải thương lượng lại?

Không chỉ lúc khởi động. Cần negotiation lại khi:

1. Host nâng API version hoặc thay đổi required capabilities.
2. Plugin được hot-reload hoặc thay JAR/provider.
3. Tạo `ModuleLayer` hoặc classloader mới cho nhóm plugin mới.
4. Chuyển workload sang chế độ mới cần feature khác (ví dụ `AUDIT`).
5. Plugin báo runtime capability degradation có thể kiểm chứng được.

Mỗi lần publish plugin set mới nên thực hiện handshake và health check **trước atomic switch**. Request đang chạy với plugin cũ cần hoàn tất hoặc bị hủy theo policy, không đổi provider giữa một transaction đang diễn ra.

Không cache kết quả negotiation chỉ theo provider name: cùng tên có thể xuất hiện ở nhiều version/layer. Cache key nên gồm artifact identity/version, contract revision, required capabilities và execution environment khi có liên quan.

## 10. Binary compatibility và limits của negotiation

Negotiation chỉ hoạt động nếu host có thể **đọc metadata** hoặc gọi **handshake API ổn định**. Nếu Java class đã bị thay signature incompatibly, quá trình load/link có thể thất bại trước khi gọi `descriptor()`.

Các ví dụ breaking changes cần lưu ý:

- Xóa hoặc đổi chữ ký method mà bytecode plugin cũ gọi: có thể gây `NoSuchMethodError`.
- Đổi static/instance method hoặc kiểu field: có thể gây `IncompatibleClassChangeError`.
- Đổi interface hierarchy hoặc duplicate interface class qua loaders: có thể gây class identity mismatch.
- Thêm abstract method vào SPI interface có thể khiến provider cũ compile được trước đây nhưng gây `AbstractMethodError` khi host gọi method mới.
- Đổi meaning của field/enum mà không tăng major: Java có thể link được nhưng semantics sai.

Vì thế nên phân tầng: **artifact manifest metadata** đủ ổn định để preflight trước khi nạp, **SPI handshake** nhỏ và duy trì tương thích, rồi **capability validation** chi tiết. Không cố catch mọi `LinkageError` rồi ép dùng plugin nguy hiểm; isolate lỗi và fail closed.

## 11. Kiểm thử compatibility matrix

| Test | Kỳ vọng |
| --- | --- |
| Cùng major, minor nằm range, đủ required capabilities | Accept |
| Sai major | Reject trước activate |
| Minor dưới min hoặc trên max | Reject có reason rõ |
| Thiếu một trong nhiều required capabilities | Reject, liệt kê capability thiếu |
| Có extra optional capability | Accept nhưng host chỉ dùng khi hỗ trợ |
| Descriptor null, range ngược hoặc capability unknown | Reject/validation error |
| Provider constructor ném lỗi | Không route request; cleanup partial resources |
| SDK artifact khác version binary-incompatible | Linkage fail được cô lập, không đánh dấu READY |
| Reload cùng tên provider với version khác | Negotiation lại theo artifact identity |
| Runtime mất quyền/network hoặc JDK prerequisite | Fail health check hoặc degrade theo policy |

Test nên chạy trên **artifact JAR được phát hành thật**, cùng module path/classloader setup với production. Không chỉ dùng mock provider trên classpath IDE; mock không phát hiện vấn đề SPI descriptor, module resolution hay Java binary linkage.

## 12. Checklist triển khai

- [ ] Hợp đồng API định nghĩa rõ version semantics, breaking changes và capability semantics.
- [ ] Tách required và optional capabilities theo workload.
- [ ] Có descriptor có cấu trúc, validate null/range/capability values.
- [ ] Kiểm tra artifact metadata trước khi tạo provider nếu có thể.
- [ ] Giữ handshake SPI tối thiểu và stable, một API class identity chia sẻ.
- [ ] Fail-fast khi major/range/capability không đáp ứng; không register provider bị reject.
- [ ] Báo reason code rõ và log đủ thông tin chẩn đoán.
- [ ] Không gọi optional feature trước khi kiểm tra khả năng.
- [ ] Negotiation lại khi reload, nâng host hoặc đổi workload.
- [ ] Test compatibility matrix bằng JAR/module path cuối cùng.

**Kết luận:** nạp được provider chỉ là bước khám phá. Host phải **đàm phán hợp đồng và khả năng** theo quy tắc tường minh, từ chối sớm những plugin có API version hoặc capability không phù hợp và chỉ kích hoạt provider đã qua kiểm tra. Đây là điều kiện quan trọng để hệ thống Java mở rộng động mà vẫn giữ tính đúng đắn khi SDK và plugin được phát hành độc lập.
