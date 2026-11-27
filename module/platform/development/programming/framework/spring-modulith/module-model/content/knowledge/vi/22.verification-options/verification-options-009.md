# Không tắt verification chỉ để build xanh

## Vì sao cần giữ bước kiểm chứng kiến trúc

Trong một ứng dụng Spring Boot được tổ chức theo modular monolith, các module nghiệp vụ có ranh giới rõ ràng và giao tiếp qua API đã công bố. Spring Modulith giúp mô hình hóa những ranh giới đó, đồng thời kiểm tra quan hệ phụ thuộc giữa các package. Lệnh kiểm chứng kiến trúc vì thế là một hàng rào bảo vệ thiết kế của ứng dụng.

Khi ApplicationModules.verify() phát hiện vi phạm, build thất bại là hành vi có chủ đích. Kết quả đó báo rằng mã nguồn hiện tại đã vượt qua một ranh giới module, tạo chu trình phụ thuộc hoặc sử dụng một phần nội bộ chưa được công bố. Xóa lời gọi kiểm chứng, đánh dấu test bị bỏ qua hoặc bắt lỗi rồi bỏ qua có thể làm build xanh trở lại, nhưng cũng loại bỏ tín hiệu cho biết kiến trúc đang lệch khỏi quy tắc đã chọn.

Build thành công chỉ có ý nghĩa khi các bước kiểm tra cần thiết thực sự được chạy và đạt yêu cầu. Nếu test kiến trúc không chạy, trạng thái xanh không chứng minh rằng các module vẫn độc lập và có thể thay đổi an toàn.

## Verification kiểm tra điều gì?

Một bài kiểm tra cấu trúc thường tạo mô hình từ lớp ứng dụng Spring Boot rồi gọi verify():

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModularStructure() {
        ApplicationModules.of(Application.class).verify();
    }
}
~~~

Application.class nên là lớp ứng dụng nằm ở package gốc để Spring Modulith có thể phát hiện các module thuộc ứng dụng. Bài kiểm tra này không cần khởi động toàn bộ Spring Application Context; nó kiểm tra cấu trúc module được suy ra từ mã nguồn.

Tùy cấu trúc và metadata của ứng dụng, bước kiểm chứng có thể phát hiện các vấn đề như:

- Hai module phụ thuộc vòng tròn, khiến ranh giới và thứ tự thay đổi giữa chúng trở nên khó kiểm soát.
- Một module truy cập kiểu nằm trong package nội bộ của module khác.
- Một module phụ thuộc vào module hoặc named interface chưa được khai báo trong danh sách phụ thuộc được phép.

Đây là kiểm tra kiến trúc tĩnh. Nó không thay thế unit test, integration test hay kiểm tra hành vi runtime. Một ứng dụng vẫn cần các loại test đó để xác nhận nghiệp vụ, cấu hình Spring, giao dịch và xử lý sự kiện hoạt động đúng.

## Xử lý vi phạm theo nguyên nhân

Trước khi thay đổi cấu hình, hãy đọc toàn bộ thông báo vi phạm và xác định module nguồn, module đích, package hoặc kiểu đang bị truy cập. Chọn cách sửa theo ý nghĩa nghiệp vụ của quan hệ phụ thuộc.

### 1. Phụ thuộc là hợp lệ và cần được khai báo

Ví dụ, module orders cần gọi API công khai của module catalog. Nếu đây là quan hệ nghiệp vụ có chủ đích, khai báo nó trong package-info.java của module orders:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog"
)
package com.acme.orders;
~~~

Khai báo này thể hiện hướng phụ thuộc được cho phép từ orders sang catalog. Danh sách nên chỉ chứa những module mà orders thực sự cần. Không thêm hàng loạt module vào danh sách chỉ để làm biến mất thông báo lỗi, vì như vậy quy tắc phụ thuộc sẽ mất tác dụng.

### 2. Module đang truy cập package nội bộ

Một module có thể được phép phụ thuộc vào catalog nhưng vẫn không được truy cập tùy ý mọi package bên trong module đó. Theo mặc định, Spring Modulith phân biệt API công khai của module với các package nội bộ. Nếu một package con cần trở thành một phần API có chủ đích, hãy công bố nó dưới dạng named interface.

Ví dụ, package com.acme.catalog.api có thể được đánh dấu như sau:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.catalog.api;
~~~

Module orders có thể giới hạn phụ thuộc vào named interface này:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog::api"
)
package com.acme.orders;
~~~

Named interface tạo ra một điểm truy cập được công bố rõ ràng. Những package triển khai như com.acme.catalog.internal vẫn có thể được giữ kín để module sở hữu chúng tự do thay đổi.

### 3. Vi phạm xuất phát từ phụ thuộc vòng tròn

Giả sử orders gọi shipping, đồng thời shipping cũng gọi trực tiếp orders. Việc cho phép cả hai chiều chỉ che đi triệu chứng và làm hai module gắn chặt với nhau.

Hãy xem xét một trong các hướng thiết kế sau:

- Đưa quy tắc nghiệp vụ về module thực sự sở hữu nó, để chỉ còn một chiều phụ thuộc.
- Định nghĩa một abstraction tại phía cần sử dụng và để module còn lại cung cấp cách triển khai phù hợp.
- Dùng domain event khi module cần thông báo một sự kiện đã xảy ra mà không cần gọi trực tiếp module phát sinh sự kiện.
- Tách một khái niệm dùng chung thành module có trách nhiệm và API rõ ràng, nếu nó thực sự có vòng đời độc lập.

Sau khi thay đổi, chạy lại kiểm chứng để chắc chắn chu trình đã được loại bỏ khỏi đồ thị phụ thuộc.

### 4. Ranh giới module chưa phản ánh đúng nghiệp vụ

Nếu nhiều package luôn phải truy cập lẫn nhau để hoàn thành một nghiệp vụ, có thể chúng đang thuộc cùng một module hoặc ranh giới hiện tại chưa hợp lý. Hãy kiểm tra package gốc, vị trí lớp điều phối và quyền sở hữu dữ liệu/nghiệp vụ. Chỉ thay đổi ranh giới khi mô hình mới phản ánh đúng trách nhiệm của hệ thống; không di chuyển package tùy tiện để né một lỗi kiểm chứng.

## Những cách làm khiến build xanh nhưng mất bảo vệ

Các cách sau làm cho lỗi kiến trúc không còn khiến pipeline thất bại:

~~~java
@Test
@Disabled("Tạm bỏ qua để build thành công")
void verifiesModularStructure() {
    ApplicationModules.of(Application.class).verify();
}
~~~

Những biến thể tương tự cũng có vấn đề:

- Xóa lời gọi verify() nhưng vẫn giữ một test có tên gợi ý rằng kiến trúc đang được kiểm tra.
- Bắt exception từ verify() rồi không ném lại, khiến test luôn thành công.
- Đặt test vào nhóm bị loại khỏi pipeline CI hoặc bật tùy chọn bỏ qua toàn bộ test khi build.
- Thêm điều kiện để test tự bỏ qua trên CI, môi trường tích hợp hoặc nhánh phát hành.
- Nới quy tắc phụ thuộc trên diện rộng mà không xác nhận quan hệ đó có hợp lý về nghiệp vụ hay không.

Những thay đổi này làm giảm độ tin cậy của pipeline. Người đọc log có thể thấy build thành công nhưng không biết hàng rào kiến trúc đã bị vô hiệu hóa.

## Khi nào được phép thay đổi quy tắc?

Quy tắc kiểm chứng có thể thay đổi khi kiến trúc thực sự thay đổi. Ví dụ, một module mới được tạo ra, một API được công bố cho module khác hoặc một quan hệ phụ thuộc hợp lệ được bổ sung. Khi đó, hãy cập nhật metadata tại đúng module sở hữu quy tắc và giữ phạm vi khai báo hẹp.

Nếu một module được thiết kế có chủ đích để mở cho các module khác truy cập, có thể mô hình hóa tính chất đó bằng kiểu module phù hợp của Spring Modulith, chẳng hạn @ApplicationModule(type = ApplicationModule.Type.OPEN) ở package gốc. Đây là quyết định về hợp đồng kiến trúc: module chấp nhận phạm vi truy cập rộng hơn. Chỉ sử dụng khi đó là chủ đích thiết kế và nhóm phát triển hiểu hệ quả; không dùng nó như nút tắt cho một vi phạm đơn lẻ.

Với hệ thống cũ có nhiều vi phạm, hãy xử lý theo từng nhóm nhỏ: ghi nhận vi phạm, xác định chủ sở hữu, sửa một nhóm có cùng nguyên nhân rồi chạy lại kiểm chứng. Nếu cần theo dõi phần còn tồn đọng, hãy quản lý nó bằng công việc kỹ thuật có người phụ trách và tiêu chí hoàn tất rõ ràng. Không biến việc bỏ qua test thành trạng thái mặc định của dự án.

## Giữ verification trong quy trình phát triển

Đặt test gọi ApplicationModules.verify() trong source set test thông thường để lệnh test mặc định của dự án thực thi nó. Pipeline CI cần chạy cùng nhóm test trước khi cho phép hợp nhất thay đổi. Khi một thay đổi làm test thất bại, log kiểm chứng phải được xem như phản hồi về thiết kế cần xử lý.

Một quy trình thực tế có thể thực hiện theo thứ tự sau:

1. Chạy test kiến trúc cùng các test thông thường sau khi thay đổi package hoặc phụ thuộc.
2. Đọc thông báo để xác định module nguồn, module đích và kiểu/package gây vi phạm.
3. Quyết định đó là lỗi thiết kế, API chưa được công bố, metadata còn thiếu hay ranh giới module cần xem xét lại.
4. Sửa mã nguồn hoặc khai báo đúng quy tắc kiến trúc với phạm vi nhỏ nhất.
5. Chạy lại test và xác nhận verify() thực sự được thực thi trong CI.

Nếu cần tạm thời giữ một thay đổi đang bị chặn, hãy ghi nhận nguyên nhân, người chịu trách nhiệm và thời điểm xử lý; đồng thời giữ trạng thái kiểm chứng trung thực để nhóm biết rủi ro đang tồn tại. Không báo rằng kiến trúc đã đạt khi test bị vô hiệu hóa.

## Tình huống thực hành

Một nhóm phát triển thêm chức năng đặt hàng. Module orders gọi trực tiếp com.acme.catalog.internal.ProductRepository để lấy thông tin sản phẩm. Test ModularityTests thất bại vì orders đang sử dụng package nội bộ của catalog.

Hãy xử lý theo các câu hỏi sau:

1. orders có thực sự cần truy cập repository của catalog, hay chỉ cần một API tra cứu sản phẩm?
2. Module catalog nên công bố kiểu hoặc thao tác nào để đáp ứng nhu cầu đó?
3. Package chứa API công khai có cần được đánh dấu bằng @NamedInterface không?
4. Module orders cần khai báo phụ thuộc nào trong @ApplicationModule?
5. Sau khi sửa, test kiến trúc có tiếp tục chạy trong lệnh CI mặc định không?

Một hướng giải quyết thường phù hợp là để catalog cung cấp API tra cứu sản phẩm, công bố API đó ở package gốc hoặc named interface, rồi cho phép orders phụ thuộc đúng vào API đã công bố. Test verify() tiếp tục chạy để ngăn các thay đổi sau này truy cập ngược vào phần triển khai nội bộ.

## Tiêu chí hoàn tất

Một thay đổi xử lý lỗi verification được xem là hoàn tất khi quan hệ phụ thuộc mới phản ánh đúng thiết kế nghiệp vụ, API công khai được xác định rõ, các package nội bộ vẫn được bảo vệ và bài kiểm tra kiến trúc vẫn được thực thi trong pipeline. Build xanh khi đó là bằng chứng rằng mã nguồn đáp ứng các quy tắc đã thống nhất, thay vì kết quả của việc bỏ qua chính những quy tắc ấy.
