# Labels, tags và quản lý vòng đời tài nguyên trên Google Cloud

> **Chương:** Hệ thống tài nguyên và vị trí  
> **Phạm vi học:** Mô-đun **CLOUD_PROVIDERS_GCP** hướng dẫn tổ chức project, IAM và VPC; lựa chọn Compute Engine, GKE, Cloud Run, lưu trữ, cơ sở dữ liệu; bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy, chi phí. Trong chương này, labels, Resource Manager tags và các quy trình quản lý vòng đời là công cụ giúp quản trị nhất quán tài nguyên ở những phạm vi đó.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích sự khác biệt giữa **labels**, **Resource Manager tags** và **Compute Engine network tags**.
2. Xây dựng quy ước metadata có thể dùng để tìm kiếm, phân loại, phân bổ chi phí và áp dụng chính sách.
3. Mô tả **TagKey**, **TagValue**, **TagBinding**, tag kế thừa và mối liên hệ với organization, folder, project.
4. Phân tích việc tạo, vận hành, thay đổi, lưu giữ, ngừng sử dụng và xóa tài nguyên một cách an toàn.
5. Thực hành đọc labels và quản lý một số labels qua Google Cloud CLI; kiểm tra tính phù hợp với quyền, dịch vụ và chính sách hiện có.
6. Thiết kế một quy trình quản trị cho môi trường dev, staging, production có kiểm soát chi phí và bảo mật.

## 1. Vì sao tài nguyên cloud cần metadata và vòng đời rõ ràng?

Hãy hình dung một doanh nghiệp có hàng trăm máy ảo, bucket, dịch vụ Cloud Run và cơ sở dữ liệu trong nhiều project. Một nhóm trực vận hành nhận thông báo chi phí tăng và cần trả lời ngay:

- Tài nguyên nào thuộc hệ thống thanh toán?
- Tài nguyên nào là production, tài nguyên nào chỉ dùng để thử nghiệm?
- Ai chịu trách nhiệm phê duyệt thay đổi hoặc xóa tài nguyên?
- Những tài nguyên nào cần chính sách bảo vệ nghiêm ngặt hơn?
- Tài nguyên thử nghiệm nào đã hết hạn nhưng vẫn tạo chi phí?
- Có thể xác định tác động khi một project, region hoặc dịch vụ bị thay đổi hay không?

Tên tài nguyên và project ID có ích nhưng chưa đủ cho quản trị lâu dài. Cần bổ sung **metadata có quy ước**, **ranh giới quyền** và **quy trình vòng đời**. Google Cloud cung cấp nhiều cơ chế khác nhau; chúng không thay thế lẫn nhau.

Một mô hình suy nghĩ hữu ích:

~~~mermaid
flowchart LR
    H["Resource hierarchy: organization / folder / project"] --> R["Tài nguyên cloud"]
    L["Labels: phân loại và báo cáo"] -. "Gắn metadata nơi hỗ trợ" .-> R
    T["Resource Manager tags: phân loại cho chính sách"] -. "TagBinding và kế thừa" .-> R
    N["Network tags: chọn đích firewall/routing VM"] -. "Phạm vi Compute Engine" .-> R
    P["Lifecycle: tạo → vận hành → loại bỏ"] --> R
~~~

Việc gắn metadata không tự động làm ứng dụng an toàn, giảm hóa đơn hoặc xóa tài nguyên cũ. Tổ chức phải xây dựng các quy tắc sử dụng metadata và công cụ thực thi phù hợp.

## 2. Labels: metadata nhẹ để phân loại và phân bổ chi phí

**Label** là cặp khóa–giá trị (key–value) được gắn vào những loại tài nguyên Google Cloud có hỗ trợ labels. Ví dụ, một máy ảo có thể mang:

~~~yaml
labels:
  environment: production
  application: checkout
  team: payments
  cost_center: fin001
  managed_by: terraform
~~~

Ở đây, label **environment=production** mô tả mục đích sử dụng, **team=payments** xác định nhóm vận hành, **cost_center=fin001** giúp phân tích chi phí.

### 2.1. Labels dùng để làm gì?

| Nhu cầu | Cách tận dụng label | Giới hạn cần nhớ |
|---|---|---|
| Tìm kiếm và kiểm kê | Lọc tài nguyên có application=checkout hoặc environment=dev | Chỉ những tài nguyên có hỗ trợ và đã được gắn nhãn mới có dữ liệu cần tìm |
| Phân bổ chi phí | Nhóm dữ liệu billing theo cost_center, application hoặc team | Phụ thuộc khả năng xuất thông tin label của từng dịch vụ và thời điểm phát sinh chi phí |
| Báo cáo vận hành | Xác định đơn vị chịu trách nhiệm, phân loại nguồn lực | Label không thay thế IAM, Cloud Monitoring hoặc CMDB |
| Dọn dẹp môi trường thử nghiệm | Dùng expires_on hoặc lifecycle=temporary để đưa vào danh sách rà soát | Nhãn không tự xóa, dừng hoặc giải phóng tài nguyên |
| Kiểm soát chuẩn đặt tên | Kiểm tra tính đầy đủ của các nhãn bắt buộc bằng pipeline | Phải có bước kiểm tra/khắc phục vì không phải mọi loại tài nguyên đều hỗ trợ nhãn |

**Điểm cốt lõi:** label phục vụ **mô tả và quản trị**. Gắn label **environment=production** không tự biến tài nguyên thành production an toàn; IAM, backup, mạng và phát hành vẫn phải được cấu hình.

### 2.2. Quy ước đặt key và value

Quy tắc cụ thể phụ thuộc loại tài nguyên/API, nhưng lựa chọn an toàn, dễ dùng với nhiều dịch vụ là:

- Key ngắn, chữ thường, rõ nghĩa, ví dụ **environment**, **application**, **team**, **cost_center**.
- Value có tập từ vựng giới hạn: **production**, **staging**, **development** thay vì trộn các biến thể như **prod**, **prd**, **production**.
- Dùng chữ thường, chữ số, dấu gạch ngang hoặc dấu gạch dưới khi được dịch vụ hỗ trợ; tránh dấu cách và ký tự đặc biệt trong bộ quy ước chung.
- Nhiều API giới hạn độ dài key/value và số label trên tài nguyên. Trước khi áp dụng hàng loạt, kiểm tra giới hạn tài nguyên đích.
- Không đưa mật khẩu, khóa, token, thông tin cá nhân hoặc nội dung nhạy cảm vào key/value. Metadata có thể được hiển thị cho nhiều vai trò quản trị và đưa vào báo cáo.

**Ví dụ từ vựng thống nhất:**

| Key | Các value mẫu | Ý nghĩa |
|---|---|---|
| environment | development, staging, production | Môi trường triển khai |
| application | checkout, catalog, inventory | Dịch vụ hoặc ứng dụng |
| team | payments, platform, data | Nhóm chịu trách nhiệm |
| cost_center | fin001, ops002 | Trung tâm chi phí |
| managed_by | terraform, pipeline, manual | Cách quản lý tài nguyên |
| lifecycle | permanent, temporary | Phân loại vòng đời dự kiến |
| expires_on | 20261231 | Ngày phải rà soát; định dạng YYYYMMDD trong quy ước nội bộ |

Value **expires_on=20261231** không có hiệu lực xóa tài nguyên. Một quy trình khác phải đọc ngày hết hạn, xác nhận chủ sở hữu, kiểm tra phụ thuộc và phê duyệt thao tác nếu cần.

### 2.3. Label không tự kế thừa theo cây tài nguyên

Giả sử folder **commerce** chứa project **shop-prod**. Gắn label **team=payments** vào project không có nghĩa mọi bucket, VM và dịch vụ dưới project sẽ tự có label đó. Hãy phân biệt:

- **Project labels:** metadata của chính project.
- **Resource labels:** metadata trên từng tài nguyên có hỗ trợ labels.
- **Báo cáo chi phí:** có thể chứa trường về project và tài nguyên riêng, nhưng cách biểu diễn khác theo nguồn dữ liệu và dịch vụ.

Do đó, nếu báo cáo cần phân tích theo nhãn tài nguyên, pipeline hoặc module hạ tầng phải gắn nhãn ở **đúng cấp**. Không được giả định “gắn nhãn project một lần là mọi tài nguyên có cùng nhãn”.

## 3. Resource Manager tags: metadata phục vụ chính sách

Trong Google Cloud, **Resource Manager tags** cũng là cặp key–value nhưng có cấu trúc riêng và khả năng kết hợp với **IAM Conditions**, **Organization Policy** cùng một số tính năng được hỗ trợ khác. Đây là công cụ hữu ích khi tổ chức muốn áp dụng chính sách có điều kiện dựa trên phân loại tài nguyên.

### 3.1. Ba thành phần của tag

| Thành phần | Vai trò | Ví dụ khái niệm |
|---|---|---|
| **TagKey** | Định nghĩa thuộc tính quản trị; được tạo trong phạm vi parent được hỗ trợ như organization hoặc project | environment |
| **TagValue** | Giá trị được định nghĩa dưới TagKey | production, development |
| **TagBinding** | Liên kết một TagValue với tài nguyên được hỗ trợ | Gắn environment/production vào project shop-prod |

Đây không chỉ là chuỗi tùy ý. TagKey và TagValue là các tài nguyên có định danh riêng, còn TagBinding thể hiện quan hệ gắn tag với tài nguyên mục tiêu. Trong công cụ quản trị, chúng có thể xuất hiện dưới các dạng tên đầy đủ hoặc ID như **tagKeys/…**, **tagValues/…**. Tên hiển thị dễ đọc và định danh kỹ thuật không nên bị nhầm lẫn.

Ví dụ:

~~~text
Organization
  └── TagKey: environment
        ├── TagValue: development
        ├── TagValue: staging
        └── TagValue: production

Project: shop-prod
  └── TagBinding → environment/production
~~~

### 3.2. Kế thừa tag theo resource hierarchy

Với các tài nguyên, tính năng và phương thức đánh giá có hỗ trợ, tag gắn trên organization, folder hoặc project có thể được **kế thừa** bởi tài nguyên con. Cơ chế này khác với labels thông thường.

~~~mermaid
flowchart TD
    O["Organization"]
    F["Folder: commerce"]
    P["Project: shop-prod"]
    VM["Compute Engine: payment-vm"]
    CR["Cloud Run: checkout-api"]
    TG["TagBinding tại project: environment=production"]
    O --> F --> P
    P --> VM
    P --> CR
    TG -. "Gắn trực tiếp" .-> P
    P -. "Kế thừa tag hiệu lực khi được hỗ trợ" .-> VM
    P -. "Kế thừa tag hiệu lực khi được hỗ trợ" .-> CR
~~~

Nếu chính sách IAM có điều kiện kiểm tra tag hiệu lực, việc gắn tag tại project có thể giúp chính sách áp dụng nhất quán cho tài nguyên con mà không phải gắn một binding riêng cho từng dịch vụ. Tuy nhiên:

1. Loại tài nguyên cần **hỗ trợ tag/tag binding** hoặc cách đánh giá tag kế thừa của tính năng liên quan.
2. Chính sách sử dụng tag phải **thực sự được tạo và áp dụng**; bản thân tag không cấp hay từ chối quyền.
3. Phải kiểm tra **độ ưu tiên khi có tag kế thừa và tag gắn trực tiếp** trên cùng khóa trong tình huống sử dụng.
4. Cần có quyền thao tác với TagKey, TagValue, TagBinding và parent resource phù hợp, không mặc nhiên chỉ cần quyền Editor trên project.

### 3.3. Ví dụ tag trong điều kiện IAM

Một chính sách IAM có điều kiện có thể sử dụng biểu thức tương tự ví dụ sau để kiểm tra tag phân loại:

~~~cel
resource.matchTag('123456789012/environment', 'production')
~~~

**Ý nghĩa minh họa:** điều kiện kiểm tra tag key có namespace **123456789012/environment** và value **production** trên tài nguyên theo ngữ cảnh được IAM hỗ trợ. Chuỗi số là ví dụ, phải thay bằng namespace thực tế.

Để sử dụng trong hệ thống thật cần xác định: loại quyền đang cấp, loại tài nguyên đích, điểm gắn policy, khả năng hỗ trợ tag của dịch vụ, quyền thao tác tag và cách kiểm thử với một tài khoản có quyền hạn giới hạn. Một điều kiện đơn lẻ không bảo đảm toàn bộ hệ thống được bảo vệ.

### 3.4. Sử dụng Resource Manager tags cho Organization Policy

Một tổ chức có thể thiết kế chính sách với điều kiện gắn với tag, chẳng hạn phân loại tài nguyên production để áp dụng ràng buộc quản trị phù hợp. Không phải mọi constraint hoặc dịch vụ đều hỗ trợ cùng một dạng điều kiện dựa trên tag. Trước khi triển khai cần:

- Kiểm tra **constraint cụ thể** có hỗ trợ điều kiện hoặc xử lý tag theo cách mong muốn.
- Xem chính sách gắn ở organization, folder hay project; xác định phạm vi và kế thừa.
- Kiểm tra tác động tới tài nguyên đang hoạt động và môi trường dev/staging.
- Thử chính sách trong phạm vi hạn chế, có cách quay lại và có người chịu trách nhiệm.

Một tag **data_classification=restricted** chỉ là tín hiệu phân loại; tổ chức vẫn phải cấu hình mã hóa, IAM, mạng, lưu trú dữ liệu và quy trình xử lý thông tin tương ứng.

## 4. Phân biệt Resource Manager tags với Compute Engine network tags

Trong tài liệu và giao diện Google Cloud, từ **tag** có thể chỉ nhiều cơ chế khác nhau.

**Compute Engine network tags** là các chuỗi được gắn cho VM, thường dùng làm tiêu chí chọn đích cho một số firewall rule và route. Chúng không phải Resource Manager TagKey/TagValue/TagBinding, không phải label và không nên sử dụng như cơ chế phân bổ chi phí.

Ví dụ: VM có network tag **web-frontend**, còn một firewall rule của VPC có thể dùng network tag đó để xác định nhóm VM đích. Kết quả kiểm soát lưu lượng phụ thuộc cấu hình firewall rule, ưu tiên rule, hướng lưu lượng và các quy tắc mạng liên quan. Gắn network tag tự nó không có nghĩa cổng đã được mở.

| Tiêu chí | **Labels** | **Resource Manager tags** | **Compute Engine network tags** |
|---|---|---|---|
| Dạng dữ liệu | Key–value gắn trực tiếp vào tài nguyên hỗ trợ | TagKey/TagValue và TagBinding | Chuỗi tag trên VM |
| Mục tiêu chính | Phân loại, kiểm kê, báo cáo chi phí | Phân loại dùng trong policy có hỗ trợ | Chọn VM theo tiêu chí của firewall/route được hỗ trợ |
| Kế thừa qua hierarchy | Không tự kế thừa | Có cơ chế kế thừa trong ngữ cảnh được hỗ trợ | Không kế thừa theo organization/folder/project |
| Quản lý tập giá trị | Chủ yếu do quy ước và công cụ riêng | Giá trị được định nghĩa dưới TagKey | Quản lý qua cấu hình VM và quy ước |
| Tác động IAM/Org Policy | Không phải cơ chế cấp quyền | Có thể tham gia điều kiện chính sách hỗ trợ | Không phải Resource Manager tag để đánh giá IAM |
| Được dùng như nhãn billing | Có thể, tùy dịch vụ và dữ liệu export | Không coi là thay thế trực tiếp cho label billing | Không dùng để phân bổ chi phí qua billing label |

Ngoài network tags truyền thống, các tính năng firewall hiện đại có thể hỗ trợ những cơ chế **secure tags** hoặc định danh đích khác. Khi viết quy tắc mạng, luôn xác định chính xác **loại tag** mà sản phẩm firewall hỗ trợ; không dùng chung thuật ngữ để suy ra cùng một hành vi.

## 5. Liên hệ với organization, folder, project và vị trí tài nguyên

Một mô hình quản trị cloud được thiết kế theo nhiều lớp:

- **Organization / folder:** phân tách đơn vị quản trị, thiết lập quyền và chính sách ở cấp phù hợp.
- **Project:** ranh giới quan trọng cho API, quota, billing và nhiều quyền IAM; thường tách theo môi trường hoặc sản phẩm.
- **Resource location:** region/zone hoặc vị trí khác theo dịch vụ, quyết định độ trễ, lưu trú dữ liệu, khả năng dự phòng và một phần chi phí.
- **Labels/tags:** làm rõ chủ sở hữu, môi trường, ứng dụng, phân loại và các điều kiện chính sách.
- **Lifecycle workflow:** quyết định khi nào tài nguyên được tạo, kiểm thử, thay đổi, giữ lại, ngừng sử dụng hoặc xóa.

Ví dụ quản trị:

~~~text
Organization: example-company
  Folder: commerce
    Project: commerce-dev
      Resource Manager tag hiệu lực: environment=development
      VM labels: environment=development, team=payments
    Project: commerce-prod
      Resource Manager tag hiệu lực: environment=production
      Cloud Run labels: environment=production, application=checkout
      Cloud SQL: region theo thiết kế HA/lưu trú dữ liệu
~~~

**Lưu ý:** vị trí triển khai **không tự suy ra từ labels hoặc tags**. Gắn label **region=asia-southeast1** cũng không chuyển tài nguyên sang region đó. Ràng buộc vị trí cần được thực thi bằng cấu hình tạo tài nguyên, chính sách tổ chức phù hợp và kiểm tra pipeline.

Tương tự, tag production không thay thế việc tách quyền IAM hoặc tách project production khỏi môi trường thử nghiệm. Quyền kế thừa từ organization/folder cần được rà soát độc lập với labels/tags.

## 6. Thiết kế bộ metadata nhất quán

### 6.1. Chọn bộ chuẩn ít nhưng có giá trị

Bắt đầu bằng các câu hỏi cần trả lời thường xuyên: **ai sở hữu, phục vụ ứng dụng nào, là môi trường nào, ai chịu chi phí, được tạo bằng cách nào, khi nào cần rà soát?**

Ví dụ quy ước trong một doanh nghiệp:

| Trường | Cơ chế đề xuất | Yêu cầu mẫu |
|---|---|---|
| environment | Label và Resource Manager tag nếu cần policy | development / staging / production |
| application | Label | Mã ứng dụng được đăng ký trong danh mục nội bộ |
| team | Label | Mã nhóm vận hành có người chịu trách nhiệm |
| cost_center | Label | Mã trung tâm chi phí hợp lệ |
| managed_by | Label | terraform / pipeline / manual |
| lifecycle | Label | permanent / temporary |
| expires_on | Label cho tài nguyên tạm thời | Ngày rà soát theo YYYYMMDD |
| data_classification | Resource Manager tag nếu dùng trong chính sách | public / internal / restricted |

Không có bộ key/value trên đây là bắt buộc mặc định của Google Cloud. Đây là **quy ước mẫu**; tổ chức cần điều chỉnh theo tài nguyên hỗ trợ, chuẩn dữ liệu và công cụ kiểm soát.

### 6.2. Tránh metadata trôi dạt (drift)

Metadata drift xảy ra khi thông tin gắn trên tài nguyên không còn phản ánh thực tế. Ví dụ, một VM đổi từ nhóm platform sang nhóm payments nhưng vẫn còn **team=platform**; hóa đơn tháng sau sẽ bị phân bổ sai.

Một quy trình phòng ngừa:

1. **Nguồn chuẩn:** định nghĩa danh mục key/value và chủ sở hữu trong cấu hình được quản lý.
2. **Bắt buộc khi tạo:** pipeline hoặc mẫu IaC kiểm tra đủ các nhãn áp dụng được trước khi tạo tài nguyên.
3. **Kiểm tra định kỳ:** kiểm kê tài nguyên thiếu nhãn, giá trị không hợp lệ hoặc tài nguyên không có chủ sở hữu.
4. **Phê duyệt thay đổi:** khi chuyển team/cost center, đồng bộ thông tin billing, runbook và nhãn.
5. **Theo dõi ngoại lệ:** ghi lại tài nguyên chưa hỗ trợ label/tag hoặc chưa thể cập nhật, kèm người xử lý và thời hạn.

Không nên tự động gắn **production** chỉ vì một tài nguyên nằm trong project có chữ **prod** trong tên. Giá trị cần đến từ cấu hình nguồn và quyết định quản trị có thể kiểm chứng.

### 6.3. Tư duy “metadata là hợp đồng”

Có thể định nghĩa một hợp đồng dữ liệu đơn giản:

~~~yaml
# Quy ước nội bộ, không phải Google Cloud API manifest
required_labels:
  environment: [development, staging, production]
  team: [platform, payments, data]
  managed_by: [terraform, pipeline, manual]

conditional_labels:
  lifecycle_temporary_requires: [expires_on, team]

resource_manager_tag_keys_for_policy:
  environment: [development, staging, production]
  data_classification: [public, internal, restricted]
~~~

Hợp đồng này có thể được thực thi bằng kiểm tra IaC, cấu hình CI/CD, quy tắc kiểm kê và quy trình phê duyệt. Nó phải cho phép các ngoại lệ có lý do rõ ràng vì **khả năng gắn label/tag khác nhau theo dịch vụ**.

## 7. Vòng đời tài nguyên: từ đề xuất đến xóa bỏ

Quản trị vòng đời không chỉ là “tạo và xóa”. Một tài nguyên có thể tồn tại qua các giai đoạn **đề xuất → cấp phát → vận hành → thay đổi/mở rộng → ngừng sử dụng → lưu giữ dữ liệu cần thiết → xóa/kiểm chứng**.

~~~mermaid
flowchart TD
    A["Đề xuất: mục đích, owner, môi trường, chi phí"] --> B["Thiết kế: IAM, region, dữ liệu, backup"]
    B --> C["Tạo qua API / IaC / pipeline"]
    C --> D["Gắn labels, tags, logging và monitoring"]
    D --> E["Vận hành và kiểm tra drift/chi phí"]
    E --> F{"Còn nhu cầu?"}
    F -- "Có" --> G["Cập nhật phiên bản, cấu hình, quyền"]
    G --> E
    F -- "Không" --> H["Đánh giá phụ thuộc, lưu giữ và phục hồi"]
    H --> I["Tắt/giảm công suất khi phù hợp"]
    I --> J["Xóa có kiểm soát"]
    J --> K["Xác nhận dữ liệu, quyền, billing và inventory"]
~~~

### 7.1. Giai đoạn đề xuất và thiết kế

Trước khi cấp phát, xác định:

- **Mục đích và owner:** hệ thống nào sử dụng, ai trực vận hành, ai phê duyệt chi phí và thay đổi.
- **Phạm vi tổ chức:** tạo trong project nào, có được phép theo IAM/Organization Policy không.
- **Vị trí:** region/zone hoặc vị trí lưu trữ phù hợp yêu cầu latency, lưu trú dữ liệu, HA và khôi phục.
- **Mô hình dịch vụ:** Compute Engine, GKE, Cloud Run hoặc dịch vụ dữ liệu nào phù hợp tính chất workload.
- **Phương án bảo mật:** service account, quyền ít nhất, truy cập riêng/từ Internet, secret và log.
- **Mục tiêu vận hành:** uptime/SLO, RTO, RPO, thời hạn dữ liệu và ngân sách dự kiến.
- **Metadata:** các labels áp dụng được, Resource Manager tags cần cho policy và ngày rà soát.

Với tài nguyên thử nghiệm, nên có **ngày hết hạn và owner ngay lúc yêu cầu**. Tài nguyên không có người chịu trách nhiệm thường khó quyết định có được xóa hay không.

### 7.2. Giai đoạn cấp phát

Ưu tiên dùng **Infrastructure as Code** hoặc pipeline đã được review. Cấu hình tạo tài nguyên nên gắn metadata cùng lúc với các thuộc tính bảo mật và vị trí. Như vậy người kiểm tra thấy lý do và người sở hữu ngay trong thay đổi mã nguồn.

Ví dụ ý tưởng dùng Terraform:

~~~hcl
locals {
  common_labels = {
    environment = "production"
    application = "checkout"
    team        = "payments"
    cost_center = "fin001"
    managed_by  = "terraform"
  }
}

# Với mỗi loại tài nguyên hỗ trợ labels, truyền local.common_labels
# vào đúng thuộc tính labels của resource đó.
# Resource Manager tags được khai báo bằng tài nguyên và binding riêng.
~~~

Đây là **đoạn minh họa về cấu trúc metadata**, chưa phải cấu hình Terraform hoàn chỉnh để tạo hạ tầng. Khi áp dụng cần kiểm tra provider, schema của resource và version sử dụng. Với resource không hỗ trợ labels hoặc Resource Manager tags, pipeline phải đưa trường hợp đó vào danh sách ngoại lệ theo dõi.

### 7.3. Giai đoạn vận hành

Các vòng kiểm tra định kỳ nên trả lời:

- Có tài nguyên production nào thiếu owner hoặc cost_center?
- Tag có phản ánh đúng phân loại dữ liệu, môi trường và chính sách đang áp dụng?
- Có dịch vụ đã ngừng nhận traffic nhưng vẫn có chi phí cho instance, storage hoặc network?
- Cấu hình backup, restore, log, alert và quota có còn phù hợp với tải và mục tiêu SLO?
- Có tài nguyên tạm thời đã quá ngày rà soát?
- Có thay đổi ngoài IaC khiến trạng thái thực tế lệch cấu hình chuẩn?

Báo cáo kiểm kê không nên tự động xóa mọi tài nguyên có label **lifecycle=temporary**: có thể còn dữ liệu cần lưu, phụ thuộc mạng hoặc quy trình phân tích đang chạy.

### 7.4. Giai đoạn thay đổi và di chuyển

Thay đổi owner, đội nhóm hoặc môi trường phải cập nhật labels/tags và hệ thống phụ trợ. Việc **di chuyển vùng** không phải chỉ sửa label: nhiều dịch vụ yêu cầu tạo tài nguyên mới, sao chép dữ liệu, cập nhật endpoint, kiểm tra kết nối và chuyển traffic.

Các thay đổi tag dùng trong IAM/Organization Policy cần được đánh giá như **thay đổi chính sách bảo mật** vì một binding có thể ảnh hưởng điều kiện phân quyền hoặc ràng buộc tài nguyên. Ghi lại người thay đổi, đối tượng, lý do và tác động dự kiến.

### 7.5. Giai đoạn ngừng sử dụng và xóa

Trước khi xóa, cần phân biệt ba quyết định khác nhau:

1. **Không còn sử dụng ứng dụng:** ngừng traffic hoặc tác vụ, có thể vẫn cần giữ dữ liệu và cấu hình.
2. **Không còn cần tài nguyên đang chạy:** có thể dừng, giảm công suất hoặc xóa tài nguyên compute tùy dịch vụ và các giới hạn kỹ thuật.
3. **Được phép loại bỏ dữ liệu:** cần đáp ứng thời hạn lưu, yêu cầu kiểm toán, chính sách backup, hợp đồng và sự phụ thuộc.

Một trình tự kiểm tra:

| Bước | Nội dung | Bằng chứng nên lưu |
|---|---|---|
| Xác nhận owner | Ai phê duyệt ngừng dùng và từ thời điểm nào? | Ticket/PR có người chịu trách nhiệm |
| Kiểm tra phụ thuộc | DNS, URL, VPC, IAM, batch, database, bucket, service khác có còn dùng? | Danh sách quan hệ và kết quả kiểm thử |
| Kiểm tra dữ liệu | Có retention policy, hold, bản sao lưu, RTO/RPO hay yêu cầu lưu giữ? | Quyết định dữ liệu cần bảo toàn |
| Chặn phát sinh mới | Ngừng luồng tạo tài nguyên hoặc giao dịch theo quy trình | Bản ghi deploy/đổi lịch/đổi cấu hình |
| Thu hồi truy cập | Loại role, secret, khóa, binding không còn cần; tránh ảnh hưởng hệ thống dùng chung | Lịch sử cập nhật IAM và secret |
| Tháo gỡ và xóa | Thực hiện theo thứ tự phụ thuộc, có phương án khôi phục nếu cần | Log của pipeline hoặc ticket |
| Xác nhận hoàn tất | Inventory, trạng thái billing, monitoring, cảnh báo và tài nguyên liên quan | Báo cáo sau xóa |

Không giả định mọi tài nguyên có **soft delete** hoặc đều có thể khôi phục trong một số ngày cố định. Cơ chế phục hồi, retention lock, backup và khả năng đảo ngược phụ thuộc dịch vụ và cấu hình. Với dữ liệu quan trọng, cần **thử khôi phục trước khi quyết định xóa**.

## 8. Chi phí: kết nối labels với FinOps

Labels hữu ích cho bài toán **FinOps**: chia chi phí cloud theo người sử dụng, ứng dụng và ngân sách. Có thể xuất thông tin chi phí từ **Cloud Billing export to BigQuery** rồi tổng hợp theo metadata có trong bản ghi.

Cần hiểu ba giới hạn:

1. Không phải chi phí của mọi dịch vụ hoặc dòng billing đều kèm **resource label** chi tiết như nhau.
2. Thay đổi label hôm nay thường không làm dữ liệu chi phí lịch sử tự thay đổi theo.
3. Tag dùng cho chính sách không được mặc nhiên coi là nhãn xuất chi phí; phải kiểm tra cấu trúc dữ liệu billing sử dụng.

### 8.1. Ví dụ phân tích chi phí theo cost_center

Truy vấn minh họa trên bảng **Cloud Billing detailed/standard export** có trường labels dạng mảng:

~~~sql
-- Thay BILLING_PROJECT.BILLING_DATASET.EXPORT_TABLE bằng bảng export thật.
-- Báo cáo chi phí gộp theo label cost_center nếu bản ghi có label đó.
SELECT
  COALESCE(
    (SELECT label.value
     FROM UNNEST(labels) AS label
     WHERE label.key = 'cost_center'
     LIMIT 1),
    'unallocated'
  ) AS cost_center,
  ROUND(SUM(cost), 2) AS gross_cost
FROM `BILLING_PROJECT.BILLING_DATASET.EXPORT_TABLE`
WHERE usage_start_time >= TIMESTAMP('2026-01-01')
  AND usage_start_time < TIMESTAMP('2026-02-01')
GROUP BY cost_center
ORDER BY gross_cost DESC;
~~~

Truy vấn cộng **cost trước credits**, vì vậy đây là chi phí gộp theo dữ liệu xuất chứ không nhất thiết là số tiền cuối cùng trên hóa đơn. Để tính net cost, cần xử lý credits, điều chỉnh, loại dữ liệu và cách ghi nhận theo yêu cầu báo cáo. Giá trị **unallocated** là tín hiệu cần điều tra: bản ghi có thể không có nhãn, tài nguyên không hỗ trợ nhãn hoặc dữ liệu export không cung cấp nhãn đó.

### 8.2. Budget và cảnh báo

Có thể xây dựng ngân sách theo billing account/project và các bộ lọc mà Cloud Billing hỗ trợ. Từ đó, đội ngũ theo dõi tỷ lệ chi tiêu và xu hướng tăng chi phí.

**Budget alert không mặc nhiên là cơ chế chặn thanh toán hoặc tự xóa tài nguyên.** Nếu cần hành động tự động khi vượt ngưỡng, tổ chức phải thiết kế luồng sự kiện, quyền, kiểm tra ngoại lệ và thao tác an toàn. Không nên để một tín hiệu chi phí tự động xóa database production hoặc dữ liệu có yêu cầu lưu giữ.

### 8.3. Ví dụ mục tiêu quản trị

Một báo cáo hàng tuần có thể đưa ra:

- Tổng chi phí theo **team**, **application**, **environment**.
- Chi phí chưa phân bổ theo **cost_center**.
- VM không sử dụng, đĩa không gắn, tài nguyên tạm thời quá hạn.
- Dung lượng dữ liệu và retention ảnh hưởng tới tiền lưu trữ.
- Phần chi phí mạng ra Internet hoặc liên vùng đáng chú ý.

Dữ liệu cần được đối chiếu với owner và tải thực trước khi áp dụng quyền dừng/xóa.

## 9. IAM và policy: người nào được gắn metadata?

Labels và tags có thể tạo ra **tác động gián tiếp** quan trọng. Ví dụ, nếu một nhãn được pipeline dùng để chọn tài nguyên cần dọn dẹp, người có quyền sửa nhãn có thể ảnh hưởng tới danh sách xóa. Nếu Resource Manager tag tham gia IAM Conditions, người có quyền sửa TagBinding có thể tác động tới kết quả đánh giá truy cập.

Phân chia trách nhiệm nên bao gồm:

| Vai trò | Quyền cần cân nhắc | Rủi ro khi cấp quá rộng |
|---|---|---|
| Nhóm nền tảng | Quản lý bộ TagKey/TagValue, chính sách tổ chức và quyền binding theo phạm vi | Thay đổi phân loại và chính sách ở nhiều project |
| Nhóm ứng dụng | Gắn nhãn tài nguyên do nhóm sở hữu; thay đổi binding khi được ủy quyền | Làm sai phân bổ chi phí hoặc đánh dấu sai môi trường |
| Pipeline IaC | Tạo tài nguyên và metadata theo cấu hình đã duyệt | Nếu quyền rộng, một lỗi pipeline ảnh hưởng nhiều hệ thống |
| Nhóm FinOps | Đọc billing export, kiểm kê metadata | Lộ thông tin kinh doanh trong báo cáo hoặc truy vấn |
| Nhóm bảo mật | Rà soát IAM Conditions, Organization Policy và audit log | Đánh giá sai tác động của tag kế thừa/chính sách |

Các quyền cụ thể phụ thuộc thao tác, loại tài nguyên và API. Đối với Resource Manager tags, cần kiểm tra các vai trò/quyền quản trị tag và quyền gắn tag lên **cả tag value và tài nguyên đích** theo yêu cầu của API. Không gán vai trò quản trị rộng chỉ để một pipeline cập nhật label.

Có thể dùng audit log, thông tin phiên bản IaC và lịch sử thay đổi để truy vết. Nếu quy trình dọn dẹp tài nguyên dựa vào labels, nên có **chế độ chỉ báo cáo (dry run)**, xác minh owner và những điều kiện chặn riêng cho production.

## 10. Thực hành với Google Cloud CLI

Bài thực hành dùng một project và VM **đã được cấp sẵn**. Các lệnh đọc giúp kiểm tra metadata; lệnh ghi chỉ thực hiện khi người học có quyền và được phép thay đổi tài nguyên.

### 10.1. Đọc project và labels của VM

~~~bash
# Hiển thị project đang cấu hình trong gcloud.
gcloud config get-value project

# Xem metadata và labels của một project.
gcloud projects describe PROJECT_ID \
  --format="yaml(projectId,name,labels)"

# Xem labels trên một VM có thật trong project.
gcloud compute instances describe VM_NAME \
  --zone=ZONE \
  --project=PROJECT_ID \
  --format="yaml(name,zone,labels,tags)"

# Liệt kê VM có labels được hỗ trợ bởi API Compute Engine.
gcloud compute instances list \
  --project=PROJECT_ID \
  --format="table(name,zone,labels)"
~~~

Trong kết quả VM, trường **labels** và **tags** là hai cấu trúc riêng; trường **tags** của Compute Engine VM thường liên quan network tags, không phản ánh đầy đủ Resource Manager tags.

Lệnh đọc vẫn đòi hỏi quyền xem thích hợp và API cần thiết đã được bật. Nếu bị từ chối, không tự mở rộng quyền hoặc bật API trên project production.

### 10.2. Cập nhật và kiểm tra label

Ví dụ thêm labels lên VM thử nghiệm:

~~~bash
# Thay giá trị placeholder, kiểm tra đúng VM trước khi chạy.
# Lệnh làm thay đổi metadata thật của VM.
gcloud compute instances add-labels VM_NAME \
  --labels=environment=development,team=platform,cost_center=ops002 \
  --zone=ZONE \
  --project=PROJECT_ID

# Đọc lại labels để xác nhận.
gcloud compute instances describe VM_NAME \
  --zone=ZONE \
  --project=PROJECT_ID \
  --format="yaml(labels)"
~~~

Một tình huống đáng chú ý: đổi **team** của VM có thể làm báo cáo phân bổ chi phí từ thời điểm thay đổi khác với trước đó. Cần ghi nhận thời điểm và chủ sở hữu mới. Đối với tài nguyên được quản lý bằng Terraform, thay đổi trực tiếp bằng CLI có thể tạo **drift**; hãy điều chỉnh cấu hình nguồn và quy trình phát hành cho nhất quán.

### 10.3. Khám phá Resource Manager tags

Ví dụ thao tác **chỉ đọc** trên TagKey và TagValue đã có:

~~~bash
# Liệt kê TagKeys dưới organization nếu được cấp quyền.
gcloud resource-manager tags keys list \
  --parent=organizations/ORG_ID

# Liệt kê TagValues dưới TagKey được chọn.
gcloud resource-manager tags values list \
  --parent=tagKeys/TAG_KEY_ID
~~~

Người học cần phân biệt định danh TagKey/TagValue với các label cùng tên. Để xem hoặc thay TagBindings của một tài nguyên, phải dùng **đúng tên đầy đủ của tài nguyên**, cú pháp/phạm vi và location mà API tag binding yêu cầu. Vì khả năng gắn tag khác nhau theo loại tài nguyên, cần tham khảo hướng dẫn dành cho đối tượng cụ thể trước khi chạy lệnh tạo/xóa binding.

### 10.4. Câu hỏi quan sát

1. Project có label **team=payments** nhưng VM chưa có label đó. Truy vấn lọc theo resource label của VM có tự coi VM thuộc team payments không?
2. VM có network tag **web**. Tag này có tương đương Resource Manager TagKey **environment** không?
3. Nếu một Resource Manager tag được gắn ở cấp project, tính năng đánh giá chính sách có hỗ trợ kế thừa có thể sử dụng thông tin đó như thế nào?
4. Thêm **expires_on=20261231** có tự thiết lập lịch xóa máy không?
5. Khi đổi label cost_center, báo cáo chi phí lịch sử có tự được viết lại không?

**Gợi ý:** lần lượt: không; không; dùng tag hiệu lực để đánh giá điều kiện thích hợp; không; không nên giả định như vậy.

## 11. Tình huống thiết kế: quản trị ba môi trường của ứng dụng đặt hàng

Một nhóm phụ trách ứng dụng đặt hàng có ba project **shop-dev**, **shop-staging**, **shop-prod**. Hệ thống sử dụng Cloud Run, Cloud SQL, Cloud Storage và đôi khi có Compute Engine cho công cụ nội bộ. Nhóm đặt mục tiêu:

- Phân bổ chi phí theo ứng dụng và đội vận hành.
- Áp dụng chính sách chặt hơn cho production, không dựa vào việc đoán từ project ID.
- Tìm và rà soát tài nguyên phát triển có thời hạn.
- Bảo đảm khi đổi owner hoặc kết thúc môi trường thử nghiệm, việc dọn dẹp có kiểm chứng.

### 11.1. Thiết kế ban đầu

| Đối tượng | Metadata hoặc cách quản trị | Lý do |
|---|---|---|
| Ba project | Tag **environment** với giá trị tương ứng; project labels khi cần | Phân loại môi trường và hỗ trợ chính sách có điều kiện nếu tính năng tương thích |
| Tài nguyên hỗ trợ labels | **application=checkout**, **team=payments**, **cost_center=fin001** | Kiểm kê, phân bổ chi phí, xác định owner |
| Tài nguyên temporary | **lifecycle=temporary**, **expires_on=YYYYMMDD** | Tạo danh sách cần rà soát, không phải lịch xóa tự động |
| Cloud Run production | IAM giới hạn, service account riêng, log/metric/SLO | Kiểm soát truy cập và độ tin cậy |
| Cloud SQL | Quyết định backup, khả năng phục hồi, vị trí và quyền truy cập | Dữ liệu giao dịch cần bảo vệ độc lập với labels/tags |
| Network firewall cho VM | Sử dụng network tags hoặc selector được firewall hỗ trợ | Tách logic mạng khỏi metadata billing |
| Pipeline | Kiểm tra metadata và cấu hình trước khi cấp phát | Giảm nhãn thiếu, sai môi trường hoặc thay đổi thủ công |
| FinOps | Billing export, báo cáo unallocated và budget alert | Xác định chi phí bỏ sót và bất thường |

### 11.2. Dòng xử lý đối với môi trường thử nghiệm hết hạn

Ngày hết hạn của một VM dev đã đến. Hệ thống kiểm kê tìm thấy **lifecycle=temporary** và **expires_on** quá ngày hiện tại. Thay vì xóa ngay:

1. Tạo bản báo cáo và chuyển tới owner theo label team.
2. Kiểm tra máy còn workload, disk, địa chỉ IP hoặc dữ liệu cần giữ không.
3. Đối chiếu dependencies, mức dùng, snapshot/backup và yêu cầu retention.
4. Nếu được xác nhận ngừng dùng, thực hiện thay đổi bằng pipeline được duyệt.
5. Kiểm tra tài nguyên không còn tồn tại, không còn phát sinh chi phí, và cập nhật inventory/ticket.

Nếu VM đã bị đổi từ dev thành một tác vụ phục vụ production nhưng nhãn chưa được sửa, quy trình trên phát hiện được rủi ro chỉ khi có **bước xác minh owner và phụ thuộc**. Đây là lý do metadata và tự động hóa phải đi cùng quy trình.

### 11.3. Khi nào cần thay label bằng tag?

Không phải toàn bộ metadata đều cần là Resource Manager tag. Chỉ sử dụng tag cho thuộc tính thực sự được **chính sách hay cơ chế quản trị hỗ trợ** sử dụng, có tập giá trị chuẩn và quyền sửa được kiểm soát. Các thuộc tính phục vụ báo cáo như cost_center hoặc application thường bắt đầu bằng labels. Có thể dùng cả hai cho **environment**, nhưng cần định nghĩa **nguồn chuẩn** và cơ chế tránh trạng thái xung đột.

Ví dụ: project có tag **environment=production** nhưng một VM có label **environment=development**. Không thể quyết định quyền truy cập bằng cách nhìn label; policy đánh giá tag hoặc điều kiện được cấu hình. Ngược lại, báo cáo chi phí dựa trên label có thể nhóm VM vào development. Trường hợp này cần được phát hiện và xử lý như lỗi chất lượng metadata.

## 12. Những lỗi thường gặp và nguyên tắc ghi nhớ

| Ngộ nhận hoặc lỗi | Cách hiểu đúng |
|---|---|
| Gắn labels vào project thì toàn bộ con có labels | Labels không tự kế thừa; gắn đúng tài nguyên cần lọc/báo cáo |
| Labels là công cụ phân quyền | IAM và các chính sách mới quyết định quyền; labels phục vụ mô tả |
| Mọi “tag” trong Google Cloud là một loại | Resource Manager tags, Compute Engine network tags và các tag firewall phải được phân biệt |
| Tag production tự áp chính sách bảo mật | Chỉ có tác dụng chính sách khi đã cấu hình chính sách có hỗ trợ và kiểm thử |
| Mọi tài nguyên đều hỗ trợ nhãn/tag giống nhau | Hỗ trợ phụ thuộc sản phẩm, API và phương thức gắn |
| Đổi label làm hóa đơn cũ đổi theo | Dữ liệu billing lịch sử không mặc nhiên được viết lại |
| Có expires_on nghĩa là máy tự dừng | Label chỉ là dữ liệu; cần quy trình và công cụ thực thi |
| Xóa project là cách đơn giản để dọn tài nguyên | Có thể ảnh hưởng dữ liệu, phụ thuộc và khôi phục; cần quy trình decommission theo phạm vi |
| Budget chặn mọi khoản phí vượt mức | Budget alert chủ yếu hỗ trợ quan sát và cảnh báo |
| Mọi loại tài nguyên đều phục hồi được sau khi xóa | Khả năng khôi phục, retention và backup phụ thuộc dịch vụ/cấu hình |

## 13. Bài tự kiểm tra thiết kế

Giả sử bạn phải tiếp nhận một project chưa có quy ước metadata. Hãy đề xuất:

1. Năm label tối thiểu để xác định môi trường, ứng dụng, nhóm sở hữu, trung tâm chi phí và cách cấp phát.
2. Một TagKey và tập TagValue phù hợp để phục vụ điều kiện chính sách theo môi trường.
3. Cách xử lý khi project mang tag production nhưng tài nguyên báo cáo label development.
4. Quy trình dọn dẹp cho một tài nguyên có expires_on đã qua ngày nhưng vẫn có người dùng.
5. Một báo cáo billing có thể chỉ ra chi phí chưa được phân bổ và các hạn chế của dữ liệu đầu vào.

Một phương án hợp lý: định nghĩa labels **environment, application, team, cost_center, managed_by**; dùng Resource Manager TagKey **environment** với TagValue **development/staging/production** khi tính năng chính sách yêu cầu; kiểm tra tính nhất quán ở pipeline; xử lý tài nguyên hết hạn qua xác nhận owner, phụ thuộc, dữ liệu và approval; dùng billing export nhóm theo cost_center đồng thời thống kê phần **unallocated**.

---

**Điểm cần mang sang các bài tiếp theo:** resource hierarchy xác định **tài nguyên thuộc phạm vi quản trị nào**; region/zone xác định **nó được triển khai ở đâu**; labels mô tả **nó phục vụ ai và được tính chi phí thế nào**; Resource Manager tags giúp **phân loại cho những chính sách có hỗ trợ**; quy trình vòng đời bảo đảm tài nguyên được cấp phát, vận hành và loại bỏ có trách nhiệm. Khi xây dựng hệ thống với Compute Engine, GKE, Cloud Run, Cloud Storage hoặc cơ sở dữ liệu, hãy thiết kế các lớp này cùng với IAM, mạng, phát hành tự động và monitoring ngay từ đầu.

