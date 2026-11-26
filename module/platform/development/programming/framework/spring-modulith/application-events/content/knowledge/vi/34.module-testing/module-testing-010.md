# Đọc kết quả module test

Kiểm thử module trong Spring Modulith tạo ra nhiều loại bằng chứng khác nhau: kiểm tra cấu trúc và ranh giới module, khởi tạo application context trong phạm vi một module, rồi xác minh hành vi của listener, application events và các thành phần nghiệp vụ. Khi test thất bại, dòng tổng kết chỉ cho biết có vấn đề; muốn sửa đúng cần xác định test đang kiểm tra lớp nào, lỗi xuất hiện ở giai đoạn nào và nguyên nhân gốc nằm ở đâu.

Đọc kết quả module test là quá trình đi từ tổng quan tới chi tiết: xác định phạm vi test, phân biệt lỗi kiến trúc với lỗi thực thi, tìm exception đầu tiên có ý nghĩa, đối chiếu với module và dependency liên quan, sau đó xác minh lại bằng kết quả mới. Không nên sửa code chỉ dựa vào tên test hoặc dòng cuối của stack trace.

## 1. Hai loại kết quả cần phân biệt

Spring Modulith cung cấp hai hướng kiểm tra thường gặp:

- **Kiểm tra cấu trúc module:** dùng mô hình application modules để phát hiện dependency vi phạm ranh giới, chu trình phụ thuộc và các tham chiếu không được phép.
- **Kiểm thử module:** khởi tạo Spring application context trong phạm vi module được chọn và chạy test nghiệp vụ, integration hoặc event listener.

Kiểm tra cấu trúc thường được gọi bằng **ApplicationModules.verify()**. Kiểm thử module thường dùng annotation **@ApplicationModuleTest** để giới hạn phạm vi context.

Hai kết quả này bổ sung cho nhau. Một module có thể vượt qua kiểm tra cấu trúc nhưng test nghiệp vụ vẫn thất bại do logic hoặc cấu hình. Ngược lại, test nghiệp vụ có thể chạy thành công trong khi một module khác đang phụ thuộc trực tiếp vào package nội bộ mà kiến trúc không cho phép.

| Kết quả | Trả lời câu hỏi | Không chứng minh điều gì |
|---|---|---|
| Module structure verification | Các module có tuân thủ dependency và ranh giới đã khai báo không? | Không chứng minh mọi nghiệp vụ chạy đúng |
| Module integration test | Module có khởi tạo và thực hiện hành vi được test không? | Không chứng minh toàn bộ kiến trúc module hợp lệ |
| Event/listener test | Event có được phát và listener xử lý theo kỳ vọng không? | Không chứng minh mọi đường giao event production đều hoạt động |
| Full application test | Các thành phần được khởi tạo cùng nhau có hoạt động trong phạm vi test không? | Không thay thế việc kiểm tra riêng từng ranh giới module |

## 2. Đọc kết quả tổng quan trước

Khi mở kết quả từ IDE, Maven hoặc Gradle, bắt đầu bằng các thông tin:

1. Test task hoặc test suite nào vừa chạy.
2. Tổng số test được phát hiện.
3. Số test thành công, thất bại, lỗi khởi tạo và bị bỏ qua.
4. Test class đầu tiên thất bại.
5. Có lỗi cấu hình hoặc lỗi khởi tạo context xuất hiện trước các assertion hay không.
6. Report HTML/XML có được tạo và chứa stack trace đầy đủ không.

Tên trạng thái có thể khác nhau theo công cụ. JUnit Platform thường phân biệt test successful, failed và aborted; Gradle hoặc Maven có cách tổng hợp riêng. Hãy đọc trạng thái trong report của công cụ thực tế, không suy luận rằng mọi mục bị bỏ qua đều là lỗi.

Một bảng tổng quan ví dụ:

| Chỉ số | Kết quả minh họa | Cách đọc |
|---|---:|---|
| Tests discovered | 42 | Có 42 test được phát hiện |
| Successful | 39 | Test hoàn tất và assertion đạt |
| Failed | 2 | Test chạy nhưng assertion hoặc điều kiện kỳ vọng không đạt |
| Aborted/skipped | 1 | Test không hoàn tất theo điều kiện chạy hoặc bị bỏ qua |
| Context failures | 1 | Có thể kéo theo nhiều test không chạy được |

Đừng chỉ nhìn tỷ lệ pass. Một lỗi khởi tạo context ở module dùng chung có thể làm nhiều test khác thất bại theo dây chuyền. Ưu tiên tìm lỗi đầu tiên theo thời gian và nguyên nhân gốc, sau đó mới đánh giá các lỗi còn lại có độc lập hay không.

## 3. Đọc kết quả kiểm tra cấu trúc với ApplicationModules.verify()

Một test cấu trúc thường có dạng:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
~~~

**Application** ở đây là class ứng dụng Spring Boot của dự án. **ApplicationModules.of(...)** phân tích cấu trúc module theo package và metadata mà Spring Modulith nhận diện. Lời gọi **verify()** thất bại nếu phát hiện các vi phạm theo quy tắc modularity đang áp dụng.

Khi test này thất bại, đọc phần mô tả violation trước stack trace. Thông tin cần tìm gồm:

- Module nguồn đang tạo dependency.
- Module đích bị phụ thuộc.
- Package hoặc type được tham chiếu.
- Quy tắc ranh giới bị vi phạm.
- Có chu trình dependency hoặc tham chiếu tới package nội bộ không.

Ví dụ về một dạng vi phạm:

~~~text
Module 'orders' depends on non-exposed type
'com.example.inventory.internal.StockRepository'
~~~

Thông điệp minh họa cho biết module Orders đang tham chiếu một type nội bộ của Inventory. Cần kiểm tra module Inventory có public API hoặc named interface phù hợp không, và module Orders có nên phụ thuộc vào abstraction được công bố hay không.

Không sửa lỗi bằng cách mở toàn bộ package nội bộ chỉ để test pass. Hãy xem lại ownership của type, API mà module cung cấp và hướng dependency hợp lý. Nếu type thực sự là hợp đồng giữa hai module, công bố nó qua package/interface được phép theo cấu trúc dự án.

## 4. Nhận diện các nhóm vi phạm kiến trúc

Các lỗi cấu trúc thường rơi vào một số nhóm:

| Nhóm vi phạm | Dấu hiệu trong kết quả | Hướng kiểm tra |
|---|---|---|
| Dependency vào package nội bộ | Module A tham chiếu type thuộc package không được expose của module B | Named interface, public API và vị trí type |
| Chu trình module | A phụ thuộc B và B phụ thuộc lại A, trực tiếp hoặc gián tiếp | Sơ đồ dependency và trách nhiệm module |
| Dependency không được khai báo | Có tham chiếu module ngoài danh sách allowed dependencies | Metadata module và hướng gọi |
| Truy cập type không thuộc module | Type được đặt sai package hoặc package scan nhận diện sai | Package root và cấu trúc source |
| Vi phạm quy tắc tùy chỉnh | Violation xuất phát từ rule hoặc kiến trúc riêng của dự án | Rule configuration và message cụ thể |

Một dependency hợp lệ không chỉ dựa vào việc class có modifier public. Public trong Java có nghĩa truy cập được ở mức ngôn ngữ; Spring Modulith còn kiểm tra ranh giới module và các interface được công bố.

Khi có nhiều violation, nhóm chúng theo module nguồn hoặc module đích. Nhiều dòng lỗi có thể cùng bắt nguồn từ một type bị đặt sai package hoặc một API chưa được công bố. Sửa nguyên nhân chung thường giải quyết được nhiều violation hơn sửa từng dòng riêng lẻ.

## 5. Đọc kết quả @ApplicationModuleTest

**@ApplicationModuleTest** tạo application context trong phạm vi module được kiểm thử. Ví dụ:

~~~java
package com.example.orders;

import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class OrderModuleTests {

    // Các test của module Orders.
}
~~~

Vị trí package của test class giúp Spring Modulith xác định module cần kiểm thử. Nếu test class nằm sai package, framework có thể không nhận diện đúng module hoặc không bootstrap theo phạm vi mong muốn.

Khi đọc kết quả, xác định:

- Module nào được chọn làm module under test.
- Bootstrap mode nào được cấu hình.
- Module dependency nào được đưa vào context.
- Bean nào được tạo thành công.
- Bean nào thiếu, bị thay thế hoặc xung đột.
- Test thất bại khi context khởi động hay sau khi test method chạy.

Các bootstrap mode thường dùng gồm:

- **STANDALONE:** chỉ khởi tạo module đang kiểm thử cùng các thành phần nền cần thiết.
- **DIRECT_DEPENDENCIES:** đưa các module phụ thuộc trực tiếp vào context.
- **ALL_DEPENDENCIES:** đưa cả các dependency gián tiếp vào context.

Hãy đọc giá trị mode thực tế trong annotation hoặc cấu hình test. Không dựa vào giả định về mode mặc định vì lựa chọn có thể thay đổi theo phiên bản và cách dự án cấu hình.

## 6. Phân biệt lỗi khởi tạo context và lỗi assertion

Hai dạng thất bại này cần cách điều tra khác nhau.

**Context startup failure** xảy ra trước khi test method thực sự chạy. Thường gặp các dấu hiệu:

- ApplicationContext không thể khởi tạo.
- Unsatisfied dependency hoặc NoSuchBeanDefinitionException.
- BeanCreationException.
- ConfigurationProperties không bind được.
- Nhiều test sau đó báo context failure hoặc bị bỏ qua.

Trong trường hợp này, tìm exception gốc bên dưới các wrapper exception. Ví dụ BeanCreationException có thể chỉ là lớp bọc; nguyên nhân thật có thể là thiếu bean, cấu hình sai hoặc lỗi kết nối dependency.

**Assertion failure** xảy ra khi test method đã chạy nhưng kết quả không đúng kỳ vọng. Ví dụ trạng thái projection không cập nhật, event không tới listener hoặc giá trị trả về khác expected.

Không thay đổi assertion để làm test xanh nếu chưa xác định contract nghiệp vụ. Trước tiên kiểm tra dữ liệu đầu vào, transaction, thời điểm xử lý bất đồng bộ và trạng thái thực tế.

## 7. Lần theo stack trace tới nguyên nhân gốc

Khi một test thất bại, đọc stack trace theo trình tự:

1. Đọc tên test class và test method.
2. Đọc exception type và message ở đầu phần failure.
3. Tìm chuỗi **Caused by** sâu nhất có ý nghĩa.
4. Xác định frame đầu tiên thuộc source code của dự án.
5. Mở đúng dòng code và kiểm tra dữ liệu, cấu hình hoặc dependency liên quan.
6. Đối chiếu với assertion hoặc điều kiện mà test muốn chứng minh.

Không phải lúc nào Caused by cuối cùng cũng là nguyên nhân có ích nhất. Một exception do timeout có thể là hậu quả của service không phản hồi; một exception do mapping có thể là nguyên nhân đầu tiên làm listener thất bại. Hãy kết hợp message, frame thuộc code dự án và thời điểm phát sinh.

Ví dụ:

~~~text
OrderModuleTests
  -> BeanCreationException
     -> UnsatisfiedDependencyException
        -> NoSuchBeanDefinitionException:
           No qualifying bean of type 'InventoryGateway'
~~~

Kết quả này gợi ý context của module Orders không có bean InventoryGateway. Hãy kiểm tra module dependency có được đưa vào bootstrap mode hay không, adapter có nằm trong package được scan không và test có cần một test configuration hoặc mock boundary phù hợp không.

## 8. Đọc lỗi liên quan đến module dependency và bootstrap mode

Một module test có thể thất bại vì phạm vi context không chứa module mà test đang cần. Ví dụ test ở Orders gọi InventoryGateway nhưng bootstrap mode chỉ nạp module Orders.

Trước khi thêm dependency vào test, xác định quan hệ đó có hợp lệ trong kiến trúc:

- Nếu Orders được phép phụ thuộc Inventory qua named interface, chọn bootstrap mode phù hợp hoặc cấu hình boundary bean.
- Nếu Orders đang truy cập implementation nội bộ của Inventory, cần sửa thiết kế dependency.
- Nếu test chỉ cần cô lập một collaborator, có thể dùng test double tại ranh giới đã công bố.
- Nếu test cần kiểm tra tương tác thực giữa hai module, bootstrap mode cần bao gồm dependency hợp lệ.

Không dùng ALL_DEPENDENCIES để che một dependency không hợp lệ. Context rộng hơn có thể khiến test pass nhưng không sửa được vi phạm modularity.

## 9. Đọc kết quả kiểm thử application events

Trong module Spring Modulith, nhiều lỗi module test liên quan tới event publication và listener. Khi test event thất bại, cần phân biệt các giai đoạn:

| Giai đoạn | Dấu hiệu | Câu hỏi điều tra |
|---|---|---|
| Publish | Không quan sát thấy event | Publisher có được gọi trong luồng nghiệp vụ không? |
| Transaction | Listener không chạy sau rollback | Test có thực sự commit transaction không? |
| Publication | Publication chưa hoàn tất | Listener có ném exception hoặc bị dừng không? |
| Async listener | Assertion chạy quá sớm | Test có chờ điều kiện hoàn tất không? |
| Listener logic | Event tới nhưng dữ liệu sai | Mapping hoặc nghiệp vụ cập nhật projection có đúng không? |
| Externalization | Message không tới broker | Adapter, serializer và broker acknowledgment có thành công không? |

Nếu listener bất đồng bộ, test nên chờ một điều kiện có ý nghĩa bằng timeout hữu hạn. Assertion ngay sau khi publish có thể chạy trước listener và tạo false failure.

Với test publication lifecycle, kiểm tra trạng thái của Event Publication Registry sau listener success và failure. Registry theo dõi publication tới listener; nó không thay thế event store hoặc bằng chứng rằng consumer bên ngoài đã hoàn tất nghiệp vụ.

## 10. Phân biệt failed, aborted và skipped

Một test không chạy tới assertion không nhất thiết là assertion failure:

- **Failed:** test đã chạy nhưng assertion không đạt hoặc có exception không được xử lý.
- **Aborted:** test bị hủy có chủ đích hoặc điều kiện runtime khiến test không thể tiếp tục.
- **Skipped/disabled:** test không được chạy do annotation, assumption, filter hoặc cấu hình.
- **Context failure:** test không thể khởi tạo context; một số công cụ tổng hợp nó như test error/failure.

Khi thấy skipped hoặc aborted, đọc lý do trong report. Có thể đó là điều kiện test hợp lệ, ví dụ môi trường không bật integration profile. Nhưng nếu test quan trọng bị bỏ qua trong CI, cần xác minh pipeline có đang chạy đúng profile và tag hay không.

Không tính skipped như passed. Khi báo cáo chất lượng, nêu rõ số test thực sự chạy và số test không chạy.

## 11. Đọc report HTML/XML và kết quả CI

Console output thường bị rút gọn. Report HTML hoặc XML chứa thông tin chi tiết hơn:

- Test class, method và thời gian chạy.
- Exception message và stack trace.
- System output hoặc test output nếu công cụ lưu lại.
- Test bị skipped/aborted và lý do.
- Test suite hoặc module nào có failure.
- Thời điểm test bắt đầu và kết thúc.

Khi CI thất bại nhưng chạy local thành công, so sánh:

- Java version và Spring profile.
- Environment variables và application properties.
- Database/broker/service test dependencies.
- Timezone, locale và clock.
- Parallel test execution.
- Test ordering hoặc dữ liệu dùng chung.
- Resource limit và timeout.

Một test flaky có thể pass khi chạy riêng nhưng fail khi chạy song song do dùng chung database row, topic hoặc static state. Report cần được đối chiếu với log và môi trường chạy, không chỉ lặp lại test cho tới khi xanh.

## 12. Phân biệt lỗi test với lỗi môi trường

Một module test có thể thất bại vì môi trường thay vì logic module:

| Dấu hiệu | Khả năng nguyên nhân | Cách xác minh |
|---|---|---|
| Connection refused | Database hoặc broker chưa sẵn sàng | Kiểm tra test container và endpoint |
| Timeout không ổn định | Tài nguyên CI hoặc async processing chậm | Xem duration, retry và log thời điểm |
| Port already in use | Test chạy song song hoặc service cũ còn hoạt động | Xác định process và port của test |
| Missing environment variable | Profile hoặc secret test chưa được cấp | Đọc cấu hình test được chọn |
| Test pass riêng, fail cả suite | Dữ liệu dùng chung hoặc race condition | Xem thứ tự chạy và isolation |
| Khác biệt local/CI | Java, timezone, locale hoặc dependency version | So sánh runtime và resolved configuration |

Không thay đổi timeout tăng thật lớn để che một dependency bị treo. Trước tiên xác định thời gian chậm ở bước nào và liệu test có đang chờ một điều kiện không thể xảy ra.

## 13. Đọc thời gian chạy và dấu hiệu hiệu năng

Thời gian của test có thể chỉ ra vấn đề ngay cả khi tất cả đều pass:

- Một module test tăng thời gian đột ngột sau khi thêm dependency.
- Nhiều test cùng khởi tạo application context mới.
- Test bất đồng bộ thường xuyên chạm timeout.
- Test database chạy chậm do dữ liệu hoặc index tăng.
- Test module bị kéo vào quá nhiều module khác.

So sánh thời gian theo test class và theo suite qua nhiều lần chạy. Một test đơn lẻ chậm có thể do setup; nhiều test chậm cùng lúc có thể do context bootstrap hoặc hạ tầng dùng chung.

Có thể giảm chi phí bằng cách giới hạn bootstrap mode phù hợp, tái sử dụng context khi an toàn, tạo fixture nhỏ và cô lập dependency ngoài. Tuy nhiên, không thu hẹp test tới mức bỏ qua ranh giới mà test cần xác minh.

## 14. Quy trình xử lý khi module test thất bại

Một quy trình thực tế có thể đi theo thứ tự:

1. **Xác định phạm vi:** test cấu trúc, module integration hay full application.
2. **Tìm lỗi đầu tiên:** ưu tiên exception gốc và test đầu tiên thất bại.
3. **Phân loại:** violation kiến trúc, context startup, assertion, async timing, dependency hoặc môi trường.
4. **Khoanh vùng module:** xác định module nguồn, module đích và boundary liên quan.
5. **Kiểm tra bằng chứng:** stack trace, report, log, event ID và trạng thái publication nếu có.
6. **Sửa nguyên nhân:** điều chỉnh dependency, cấu hình, transaction, test fixture hoặc logic.
7. **Chạy lại test hẹp:** xác nhận lỗi cụ thể đã được giải quyết.
8. **Chạy phạm vi liên quan:** kiểm tra các module phụ thuộc và cấu trúc toàn ứng dụng.
9. **Ghi nhận kết quả:** test nào đã chạy, môi trường nào, failure nào còn tồn tại và lý do.

Không sửa nhiều lớp cùng lúc nếu chưa biết nguyên nhân. Mỗi thay đổi nên tạo ra một giả thuyết có thể kiểm chứng bằng kết quả test tiếp theo.

## 15. Checklist đọc kết quả module test

Khi xem một báo cáo, hãy xác nhận:

- Đã biết test đang kiểm tra cấu trúc module hay hành vi module.
- Đã xác định module under test và bootstrap mode.
- Đã phân biệt failed, aborted, skipped và context startup failure.
- Đã đọc exception gốc và frame đầu tiên thuộc code dự án.
- Đã kiểm tra module dependency, named interface và package boundary khi có violation.
- Đã xác minh transaction commit/rollback nếu test liên quan application event.
- Đã chờ listener bất đồng bộ bằng điều kiện và timeout rõ ràng.
- Đã kiểm tra publication state nếu test liên quan Event Publication Registry.
- Đã phân biệt lỗi logic với lỗi database, broker hoặc môi trường CI.
- Đã chạy lại test hẹp rồi xác minh phạm vi module liên quan.
- Đã ghi rõ test không chạy hoặc bị bỏ qua trong báo cáo.

Đọc kết quả module test đúng cách giúp xác định vấn đề nằm ở kiến trúc, bootstrap context, nghiệp vụ hay hạ tầng. Khi kết hợp output của ApplicationModules.verify(), report của @ApplicationModuleTest, stack trace, log và trạng thái event publication, nhóm phát triển có thể sửa đúng nguyên nhân và giữ ranh giới module Spring Modulith được kiểm soát.

