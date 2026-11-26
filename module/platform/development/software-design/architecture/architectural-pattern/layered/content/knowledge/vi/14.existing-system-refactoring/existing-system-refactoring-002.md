# Dùng kiểm thử đặc trưng để bảo vệ hành vi trước khi tái cấu trúc

Khi cải tiến một hệ thống đã chạy lâu năm, khó khăn lớn không chỉ nằm ở việc hiểu mã nguồn. Nhiều hành vi quan trọng có thể chưa được mô tả đầy đủ trong tài liệu: cách hệ thống làm tròn tiền, thứ tự áp dụng chiết khấu, quy tắc xử lý dữ liệu thiếu, mã lỗi trả về hoặc side effect được tạo ra khi một thao tác hoàn tất. Một thay đổi trông có vẻ chỉ làm sạch cấu trúc có thể vô tình làm thay đổi những hành vi mà người dùng hoặc hệ thống khác đang phụ thuộc.

**Kiểm thử đặc trưng (characterization test)** giúp ghi nhận hành vi thực tế của hệ thống trước khi thay đổi cấu trúc. Thay vì bắt đầu bằng giả định rằng mã cũ đang làm đúng điều tài liệu nói, ta tạo đầu vào có kiểm soát, quan sát đầu ra và side effect hiện tại, rồi biến những quan sát quan trọng thành kiểm thử có thể chạy lại. Các kiểm thử này tạo một lưới an toàn để thực hiện refactor từng bước.

Bài học thuộc module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED, với mục tiêu học tổ chức phần mềm theo kiến trúc phân tầng. Trong bối cảnh này, kiểm thử đặc trưng giúp làm rõ hợp đồng giữa tầng trình bày, ứng dụng, miền và truy cập dữ liệu ngay cả khi các ranh giới trong hệ thống cũ còn mờ. Mục tiêu trước mắt là bảo vệ hành vi hiện có đủ quan trọng để giữ; việc hành vi đó có nên được cải tiến hay không là một quyết định riêng cần có căn cứ.

## 1. Kiểm thử đặc trưng ghi nhận điều gì?

Một kiểm thử thông thường thường bắt đầu từ yêu cầu hoặc thiết kế đã biết: với đầu vào X, hệ thống phải trả kết quả Y. Kiểm thử đặc trưng bắt đầu từ một câu hỏi khác: với đầu vào X, hệ thống hiện tại thực sự làm gì?

Ví dụ, một hệ thống tính phí giao hàng cũ có thể có những quy tắc chưa được mô tả rõ:

- Phí được làm tròn ở từng dòng hay chỉ làm tròn tổng cuối cùng?
- Mã khu vực không nhận diện được bị từ chối hay dùng mức phí mặc định?
- Đơn hàng có trọng lượng bằng ngưỡng được xếp vào nhóm thấp hay nhóm cao?
- Phí được tính trước hay sau khi áp dụng khuyến mãi?
- Khi không truy vấn được bảng cấu hình, hệ thống trả lỗi hay dùng cấu hình cache?

Kiểm thử đặc trưng tạo các trường hợp đầu vào đại diện, chạy trên phiên bản hiện tại và ghi lại kết quả quan sát được. Những kết quả đó có thể bao gồm:

- Giá trị trả về, mã trạng thái và cấu trúc response.
- Dữ liệu được ghi, cập nhật hoặc xóa.
- Sự kiện, message, email hoặc lời gọi tới hệ thống ngoài.
- Thứ tự các thao tác có ý nghĩa đối với người gọi.
- Exception, mã lỗi và cách xử lý dữ liệu biên.

Điều cần nhớ là kết quả kiểm thử đặc trưng mô tả hành vi hiện tại, không tự chứng minh hành vi đó đúng về mặt nghiệp vụ. Nếu hệ thống hiện tại có một lỗi đã biết, kiểm thử có thể ghi nhận lỗi đó để refactor không vô tình thay đổi nó trước khi nhóm quyết định cách sửa. Khi sửa lỗi, cần thay đổi kỳ vọng một cách có chủ đích và ghi rõ lý do.

## 2. Khác biệt giữa characterization test và kiểm thử theo đặc tả

Hai loại kiểm thử có thể trông giống nhau về cú pháp, nhưng khác nhau về nguồn gốc của kỳ vọng:

| Tiêu chí | Kiểm thử theo đặc tả | Kiểm thử đặc trưng |
|---|---|---|
| Kỳ vọng đến từ đâu? | Yêu cầu, hợp đồng hoặc quyết định nghiệp vụ đã xác nhận | Hành vi quan sát được của phiên bản hiện tại |
| Câu hỏi chính | Hệ thống có làm đúng điều đã định nghĩa không? | Hệ thống hiện đang làm gì ở trường hợp này? |
| Phát hiện lỗi cũ | Có thể phát hiện nếu yêu cầu đã mô tả trường hợp đó | Có thể ghi nhận cả hành vi đúng lẫn quirks/lỗi hiện hữu |
| Mục tiêu trước refactor | Xác nhận hệ thống đáp ứng hợp đồng mong muốn | Giảm rủi ro vô tình thay đổi hành vi chưa được hiểu rõ |
| Khi thay đổi kỳ vọng | Khi đặc tả được sửa hoặc lỗi được xác nhận | Khi nhóm đã quyết định hành vi cũ cần thay đổi và chấp nhận tác động |

Một characterization test có thể trở thành regression test sau khi hành vi được hiểu và chấp nhận làm hợp đồng. Ngược lại, không nên biến mọi đầu ra tình cờ của hệ thống cũ thành cam kết dài hạn. Hãy phân biệt điều người dùng phụ thuộc, điều hệ thống tích hợp đang dựa vào và chi tiết nội bộ không cần bảo vệ.

## 3. Chọn luồng có rủi ro trước khi viết test

Không cần ghi nhận toàn bộ hệ thống cũ ngay từ đầu. Bắt đầu từ luồng có rủi ro thay đổi cao hoặc hậu quả sai lệch lớn:

- Luồng có doanh thu, thanh toán, số dư, tồn kho hoặc dữ liệu không thể dễ dàng khôi phục.
- Luồng được nhiều controller, job nền hoặc hệ thống khác cùng sử dụng.
- Thành phần có nhiều nhánh điều kiện, nhiều lần truy vấn hoặc nhiều side effect.
- Mã nguồn có ít test, ít tài liệu hoặc phụ thuộc vào thư viện/dịch vụ cũ.
- Khu vực sắp được tách tầng, đổi framework, thay persistence hoặc thay hợp đồng API.

Một cách thực tế là lập bản đồ luồng từ điểm vào đến nơi tạo ra tác động:

~~~mermaid
flowchart LR
    IN["HTTP / Job / Message"] --> P["Presentation adapter"]
    P --> A["Application orchestration"]
    A --> D["Business rules"]
    D --> R["Repository / external port"]
    R --> DB["Database / external system"]
    A --> OUT["Response / event"]
~~~

Với mỗi luồng, ghi lại đầu vào, dữ liệu quan trọng được đọc, các quyết định nghiệp vụ, thay đổi dữ liệu và side effect. Bản đồ này không cần phản ánh cấu trúc package lý tưởng; nó chỉ cần đủ để chọn các điểm quan sát có giá trị trước khi refactor.

## 4. Bắt đầu bằng quan sát từ bên ngoài

Khi hệ thống cũ khó hiểu, ưu tiên kiểm thử qua giao diện mà người dùng hoặc thành phần khác đang sử dụng: HTTP endpoint, public service method, command handler, batch job hoặc message consumer. Cách tiếp cận này giảm phụ thuộc vào tên lớp và cấu trúc nội bộ vốn có thể thay đổi trong quá trình refactor.

Ví dụ, kiểm thử một endpoint tính phí giao hàng có thể xác nhận response hiện tại:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class LegacyShippingEndpointCharacterizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void recordsCurrentShippingQuoteResponse() throws Exception {
        mvc.perform(post("/legacy/shipping/quote")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "zone": "INNER",
                      "weightKg": 4.5,
                      "declaredValue": 250000
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.currency").value("VND"))
            .andExpect(jsonPath("$.fee").isNumber())
            .andExpect(jsonPath("$.serviceCode").isNotEmpty());
    }
}
~~~

Đoạn test này minh họa việc ghi nhận hợp đồng HTTP. Khi chạy lần đầu trên hệ thống hiện tại, cần quan sát giá trị fee và serviceCode thực tế rồi quyết định có nên khóa chính xác các giá trị đó hay không. Không nên chỉ assert rằng trường tồn tại nếu giá trị chính xác là điều khách hàng hoặc hệ thống tích hợp phụ thuộc. Ngược lại, cũng không nên assert mọi header động, timestamp hoặc mã request nếu chúng thay đổi ở mỗi lần chạy và không phải hành vi cần bảo vệ.

Nếu response chứa trường không ổn định, hãy chuẩn hóa hoặc bỏ qua đúng trường đó trong phép so sánh, đồng thời giữ lại các trường có ý nghĩa. Việc chuẩn hóa không được xóa đi khác biệt quan trọng như thứ tự dòng, giá trị tiền hoặc mã trạng thái.

## 5. Dùng dữ liệu kiểm thử có kiểm soát

Một kiểm thử đặc trưng chỉ đáng tin khi đầu vào và môi trường đủ ổn định để kết quả có thể lặp lại. Hãy kiểm soát:

- **Thời gian:** truyền Clock hoặc cố định thời điểm nếu hệ thống có thể phụ thuộc ngày, giờ, múi giờ hoặc hạn hiệu lực.
- **Sinh ID/ngẫu nhiên:** dùng nguồn ID hoặc random có thể thay thế trong test nếu giá trị đó ảnh hưởng đến kết quả.
- **Dữ liệu database:** tạo fixture riêng cho từng test, xác định rõ trạng thái ban đầu và dọn dữ liệu sau test.
- **Dịch vụ ngoài:** dùng stub hoặc fake ở ranh giới mạng để không phụ thuộc trạng thái dịch vụ thật khi ghi nhận hành vi của ứng dụng.
- **Cấu hình:** cố định các feature flag, thuế suất, phí, locale và timezone có ảnh hưởng đến kết quả.

Không nên thay mọi dependency bằng mock. Nếu mục tiêu là ghi nhận cách một truy vấn SQL cũ hoạt động, cần database kiểm thử phù hợp. Nếu mục tiêu là ghi nhận cách ứng dụng phản ứng khi cổng thanh toán trả lỗi, fake cổng thanh toán là đủ và giúp test ổn định.

Một fixture nên mô tả dữ liệu có ý nghĩa thay vì phụ thuộc vào ID tình cờ của môi trường. Ví dụ, tạo khách hàng có trạng thái ACTIVE, một sản phẩm có mã SKU xác định và một đơn hàng có hai dòng hàng. Sau đó, test tập trung vào hành vi khi thực hiện ca sử dụng trên fixture này.

## 6. Tạo seam để quan sát hệ thống khó kiểm thử

Legacy code đôi khi khởi tạo trực tiếp kết nối, đọc đồng hồ hệ thống, truy cập static singleton hoặc gọi dịch vụ bên ngoài ngay bên trong logic. Những phụ thuộc này khiến test khó kiểm soát.

**Seam** là một điểm trong chương trình nơi có thể thay đổi hành vi được gọi mà không phải viết lại toàn bộ logic. Có thể tạo seam bằng cách:

- Trích xuất interface quanh một lời gọi mạng hoặc truy cập dữ liệu.
- Truyền Clock, UUID generator hoặc cấu hình qua constructor.
- Bọc một static API hoặc thư viện cũ bằng adapter nhỏ.
- Tách phần tính toán thuần khỏi phần đọc/ghi dữ liệu.
- Dùng factory để kiểm soát việc tạo implementation.

Ví dụ, thay vì đọc trực tiếp thời gian trong service:

~~~java
public class SubscriptionService {
    public boolean isExpired(Subscription subscription) {
        return subscription.getExpiresAt().isBefore(Instant.now());
    }
}
~~~

có thể đưa Clock vào:

~~~java
public class SubscriptionService {
    private final Clock clock;

    public SubscriptionService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Subscription subscription) {
        return subscription.getExpiresAt().isBefore(Instant.now(clock));
    }
}
~~~

Test có thể dùng clock cố định:

~~~java
@Test
void recordsExpirationBoundary() {
    Clock clock = Clock.fixed(
        Instant.parse("2025-05-01T00:00:00Z"),
        ZoneOffset.UTC
    );
    SubscriptionService service = new SubscriptionService(clock);

    Subscription subscription = subscriptionExpiringAt(
        Instant.parse("2025-05-01T00:00:00Z")
    );

    assertFalse(service.isExpired(subscription));
}
~~~

Ví dụ này ghi nhận quy tắc so sánh hiện tại: thời điểm hết hạn bằng thời điểm hiện tại chưa bị xem là hết hạn vì phép so sánh dùng isBefore. Nếu nghiệp vụ mong muốn hành vi khác, cần xác nhận trước khi thay kỳ vọng. Seam giúp test lặp lại chính xác mà không phụ thuộc đồng hồ thật.

Không cần tạo abstraction lớn cho mỗi static call. Hãy tạo seam nhỏ nhất đủ để kiểm soát một yếu tố gây không ổn định hoặc để quan sát một tác động quan trọng.

## 7. Ghi nhận side effect, không chỉ giá trị trả về

Một phương thức có thể trả về cùng một response nhưng tạo side effect khác nhau. Ví dụ, thao tác xác nhận đơn hàng có thể:

- Cập nhật trạng thái đơn hàng.
- Trừ tồn kho.
- Tạo bản ghi thanh toán.
- Ghi audit.
- Phát sự kiện hoặc gửi message.

Characterization test cần xác định những tác động nào là một phần của hành vi mà hệ thống khác đang dựa vào. Có thể quan sát bằng cách đọc database sau thao tác, kiểm tra fake collaborator hoặc kiểm tra message được ghi vào outbox.

Ví dụ, một service gửi thông báo qua port:

~~~java
public interface OrderNotifier {
    void orderConfirmed(UUID orderId);
}
~~~

Test dùng fake để ghi nhận lời gọi:

~~~java
class RecordingOrderNotifier implements OrderNotifier {
    private final List<UUID> confirmedOrders = new ArrayList<>();

    @Override
    public void orderConfirmed(UUID orderId) {
        confirmedOrders.add(orderId);
    }

    List<UUID> confirmedOrders() {
        return List.copyOf(confirmedOrders);
    }
}
~~~

Sau khi gọi ca sử dụng, test có thể xác nhận thông báo được phát đúng một lần với đúng mã đơn hàng. Nếu thông báo được gửi sau commit hoặc qua outbox, test cần kiểm tra đúng ranh giới đó. Không nên dùng verify số lần gọi mock để khẳng định email thực sự đã được gửi hoặc message đã được broker xác nhận.

## 8. Golden master và snapshot: dùng khi đầu ra khó mô tả

Với một hệ thống tạo báo cáo, file xuất hoặc cấu trúc JSON lớn, việc viết từng assertion có thể tốn công. **Golden master** (hay snapshot test) lưu một kết quả tham chiếu đã được quan sát và chấp nhận, rồi so sánh các lần chạy sau với kết quả đó.

Golden master hữu ích khi:

- Đầu ra có cấu trúc lớn hoặc nhiều trường phụ thuộc lẫn nhau.
- Chưa hiểu hết quy tắc tạo output nhưng cần phát hiện thay đổi ngoài dự kiến.
- Có thể chuẩn hóa timestamp, ID ngẫu nhiên hoặc thứ tự không ổn định mà không làm mất ý nghĩa.

Không nên dùng snapshot một cách mù quáng. Một snapshot có thể chứa dữ liệu cá nhân, token, thời gian hoặc thông tin môi trường; cần loại bỏ hoặc thay thế dữ liệu nhạy cảm. Snapshot quá lớn cũng khó review, và việc cập nhật snapshot hàng loạt có thể che giấu regression.

Quy trình an toàn:

1. Chạy hệ thống hiện tại với fixture cố định.
2. Xem và hiểu output thực tế.
3. Chuẩn hóa các trường không ổn định.
4. Lưu kết quả đã được review làm golden master.
5. Khi test thất bại, xem diff và xác định thay đổi có chủ đích hay vô tình.
6. Chỉ cập nhật snapshot sau khi đã hiểu và chấp nhận thay đổi.

Snapshot nên bổ sung cho assertion theo ý nghĩa, không thay thế chúng. Với giá tiền, trạng thái, mã lỗi hoặc tổng số lượng, hãy có assertion rõ ràng để người đọc hiểu điều gì đang được bảo vệ.

## 9. Từ kiểm thử đặc trưng đến refactor an toàn

Một vòng làm việc hiệu quả có thể diễn ra như sau:

~~~mermaid
flowchart TD
    A["Chọn luồng có rủi ro"] --> B["Tạo fixture và kiểm soát môi trường"]
    B --> C["Chạy phiên bản hiện tại"]
    C --> D["Quan sát output và side effect"]
    D --> E["Viết characterization tests"]
    E --> F["Chạy test và xác nhận baseline"]
    F --> G["Refactor một thay đổi nhỏ"]
    G --> H{"Tests còn pass?"}
    H -->|Có| I["Review diff và tiếp tục"]
    H -->|Không| J["Điều tra khác biệt"]
    J --> K{"Thay đổi có chủ đích?"}
    K -->|Không| L["Sửa refactor để giữ hành vi"]
    K -->|Có| M["Xác nhận quyết định, cập nhật test"]
    L --> G
    M --> I
~~~

Trình tự thực hành:

1. **Chọn một luồng nhỏ nhưng quan trọng.** Tránh bắt đầu bằng việc snapshot toàn bộ ứng dụng.
2. **Thiết lập baseline.** Chuẩn bị dữ liệu và cấu hình có thể lặp lại; chạy phiên bản cũ để ghi nhận hành vi.
3. **Viết test ở ranh giới phù hợp.** Ưu tiên API hoặc public service contract; bổ sung test sâu hơn khi cần kiểm tra một quy tắc hoặc side effect cụ thể.
4. **Xác nhận test phản ánh đúng hiện trạng.** Nếu test đỏ ngay trên phiên bản gốc, chưa thể dùng nó làm lưới an toàn cho refactor.
5. **Thực hiện một thay đổi cấu trúc nhỏ.** Ví dụ tách một lớp truy cập dữ liệu, trích xuất một hàm thuần hoặc đưa một dependency vào constructor.
6. **Chạy lại test và đọc diff.** Khi có khác biệt, xác định đó là regression, tính không ổn định của test hay một hành vi cũ cần thay đổi.
7. **Lặp lại.** Chỉ mở rộng phạm vi khi luồng hiện tại đã được bảo vệ và cấu trúc mới vẫn dễ hiểu.

Nếu test phát hiện một hành vi có vẻ sai, đừng sửa kỳ vọng chỉ để test xanh. Trước hết hãy xác minh yêu cầu, dữ liệu thực tế và các client đang phụ thuộc vào hành vi đó. Khi quyết định sửa, hãy tạo hoặc cập nhật kiểm thử theo đặc tả mong muốn và ghi nhận thay đổi như một thay đổi hành vi riêng biệt.

## 10. Khi hệ thống chưa có seam hoặc không thể chạy test dễ dàng

Một số hệ thống phụ thuộc môi trường khó dựng: database chỉ có trong mạng nội bộ, dịch vụ bên thứ ba, thiết bị phần cứng hoặc dữ liệu sản xuất lớn. Có thể bắt đầu bằng các bước nhỏ:

- Chọn một luồng có thể chạy trong môi trường kiểm thử sẵn có.
- Ghi lại request/response đã được ẩn dữ liệu nhạy cảm để làm fixture.
- Dùng adapter hoặc fake cho các dịch vụ ngoài nếu mục tiêu không phải kiểm tra chính dịch vụ đó.
- Tạo test characterization ở public API trước khi tách các lớp bên trong.
- Với truy vấn dữ liệu, dùng database kiểm thử tương thích khi cần xác nhận semantics SQL, transaction hoặc locking.
- Nếu chỉ có thể chạy thủ công, ghi rõ dữ liệu đầu vào, môi trường, bước thực hiện và kết quả quan sát; sau đó tự động hóa dần phần có thể lặp lại.

Không nên tạo một bộ test phụ thuộc vào dữ liệu production sống hoặc gây side effect thật mỗi lần chạy. Hãy sao chép dữ liệu đã được làm sạch, dùng sandbox hoặc stub ở ranh giới bên ngoài.

## 11. Tránh các bẫy thường gặp

- **Đồng nhất hành vi hiện tại với hành vi đúng:** characterization test có thể ghi lại bug. Hãy phân biệt baseline và quyết định nghiệp vụ.
- **Kiểm thử quá nhiều chi tiết nội bộ:** assert thứ tự gọi private helper hoặc cấu trúc package khiến refactor đổi tên cũng làm test hỏng. Ưu tiên hợp đồng và tác động quan sát được.
- **Fixture không ổn định:** thời gian, ID, timezone, locale hoặc dữ liệu dùng chung khiến test lúc xanh lúc đỏ. Kiểm soát các nguồn này.
- **Chỉ kiểm tra output:** bỏ qua database write, message, audit hoặc lời gọi ngoài có thể làm mất một phần hành vi.
- **Snapshot quá rộng:** thay đổi không liên quan hoặc dữ liệu nhạy cảm bị đưa vào golden master. Chuẩn hóa và review snapshot.
- **Mock quá sâu:** mock mọi repository và collaborator không thể chứng minh truy vấn, transaction hoặc mapping thật hoạt động.
- **Cập nhật expected output vội vàng:** test đỏ sau refactor không tự động có nghĩa kỳ vọng cũ sai. Điều tra trước khi cập nhật.
- **Refactor quá nhiều một lần:** khi test thất bại, khó xác định thay đổi nào gây regression. Chia nhỏ bước và giữ diff dễ review.
- **Bỏ qua tính không ổn định của hệ thống ngoài:** test dựa vào API thật, thời gian thực hoặc dịch vụ không ổn định sẽ khó làm baseline đáng tin.

## 12. Checklist trước khi bắt đầu refactor

Với mỗi luồng sắp thay đổi, hãy trả lời:

1. Người dùng hoặc hệ thống khác quan sát được hành vi nào?
2. Những đầu vào biên, nhánh lỗi và quy tắc dữ liệu nào có rủi ro cao?
3. Những bản ghi, message hoặc side effect nào phải được giữ?
4. Test có chạy được lặp lại với fixture và môi trường ổn định không?
5. Có thể quan sát qua public API hay cần tạo seam nhỏ ở dependency nào?
6. Kết quả nào là baseline hiện tại và kết quả nào đã được xác nhận là hợp đồng mong muốn?
7. Nếu test thất bại, nhóm có thể phân biệt regression với thay đổi được chấp thuận không?
8. Thay đổi refactor tiếp theo có đủ nhỏ để xác định nguyên nhân khi có lỗi không?

Kiểm thử đặc trưng không thay thế việc hiểu nghiệp vụ hoặc viết đặc tả. Nó tạo bằng chứng về hành vi hiện tại trong những khu vực tài liệu còn thiếu, giúp nhóm refactor có thể thay đổi cấu trúc mà vẫn nhận biết ngay khi một hành vi quan trọng bị đổi. Khi kết hợp với kiểm thử theo đặc tả, fixture ổn định và các bước refactor nhỏ, nó giúp cải tiến hệ thống hiện hữu an toàn và có thể kiểm chứng.
