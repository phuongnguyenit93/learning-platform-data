# Cloud Guard targets, detector recipes và responder recipes

## 1. Mục tiêu và bối cảnh

Trong chương **An toàn thông tin và kiểm toán** của module Oracle Cloud Infrastructure (OCI), bài này trình bày cách xác định phạm vi giám sát, thiết lập quy tắc phát hiện và tổ chức phản ứng với vấn đề bảo mật. Ba thành phần trung tâm là **target**, **detector recipe** và **responder recipe**.

Sau bài học, người học có thể:

- Chọn target phù hợp với cấu trúc tenancy và compartment.
- Phân biệt phát hiện cấu hình rủi ro với phát hiện hoạt động đáng chú ý.
- Clone recipe, điều chỉnh rule và gắn đúng recipe vào target.
- Phân biệt quyền quản trị Cloud Guard, quyền quan sát tài nguyên và quyền khắc phục.
- Thực hành phát hiện bucket public, xử lý có xác nhận và giới hạn tự động hóa.
- Thu thập bằng chứng để theo dõi hiệu quả, kiểm toán và bảo vệ tính sẵn sàng.

Tình huống xuyên suốt là một nhóm vận hành OCI có các môi trường production, development và phòng thực hành bảo mật. Nhóm muốn giữ được khả năng phát hiện trên diện rộng nhưng chỉ tự động sửa tài nguyên trong phạm vi đã kiểm chứng.

## 2. Ba thành phần và đường đi của một vấn đề

| Thành phần | Câu hỏi cần trả lời | Ví dụ trong bài |
| --- | --- | --- |
| Target | Phạm vi nào được kiểm tra? | Compartment phòng thực hành và các compartment con |
| Detector recipe | Điều kiện nào tạo ra vấn đề? | Bộ rule kiểm tra cấu hình lưu trữ |
| Detector rule | Dấu hiệu cụ thể nào cần phát hiện? | Bucket được cấu hình public |
| Problem | Cloud Guard đã ghi nhận điều gì? | Một phát hiện gắn với bucket cụ thể |
| Responder recipe | Có những hành động phản ứng nào? | Bộ rule thông báo và khắc phục |
| Responder rule | Hành động nào áp dụng cho vấn đề phù hợp? | Chuyển bucket sang private |

Detector tập trung vào nhận diện vấn đề; responder định nghĩa hành động phản ứng. Không phải mọi detector rule đều có một responder sửa trực tiếp tương ứng. Hành động khả dụng phụ thuộc loại tài nguyên và vấn đề. [Oracle: About OCI Detector Recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/detect-recipes-about.htm), [Oracle: About OCI Responder Recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/respond-recipes-about.htm).

~~~mermaid
flowchart TD
    A["Compartment trong phạm vi target"] --> B["Detector recipe và detector rules"]
    B --> C["Problem được ghi nhận"]
    C --> D["Responder recipe"]
    D --> E["Cloud Event để chuyển tiếp thông báo"]
    D --> F{"Rule khắc phục phù hợp?"}
    F -->|"Có: cần xác nhận"| G["Người vận hành quyết định"]
    F -->|"Có: tự động và đủ điều kiện"| H["Responder thực thi"]
    F -->|"Không"| I["Điều tra và xử lý theo runbook"]
    G --> J["Kiểm tra tài nguyên và lưu bằng chứng"]
    H --> J
    I --> J
~~~

Sơ đồ là mô hình vận hành của bài học; nó không biểu diễn thứ tự bắt buộc giữa mọi responder rule. Khi phân tích một problem, luôn xác minh rule, tài nguyên, target và hành động thực tế.

## 3. Target: thiết kế phạm vi theo compartment

### 3.1. Compartment gốc của target và cây kế thừa

Một OCI target chọn một compartment để xác định phạm vi giám sát. Các compartment con thuộc phạm vi đó, trừ nhánh đã được target khác tiếp quản. Một compartment chỉ gắn với một target có hiệu lực tại một thời điểm. [Oracle: About OCI Targets](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/targets-about.htm).

Ví dụ thiết kế:

~~~text
Tenancy root                         [target: cg-root]
├── SharedServices                   [cg-root]
├── Production                       [target: cg-production]
│   ├── App                          [cg-production]
│   └── Database                     [cg-production]
└── Development                      [target: cg-development]
    ├── TeamA                        [cg-development]
    └── SecurityLab                  [target: cg-lab]
~~~

Trong ví dụ này, tạo `cg-lab` làm cho nhánh `SecurityLab` dùng cấu hình của target riêng. Không coi `cg-development` và `cg-lab` là hai lớp rule cùng áp dụng cho bucket trong phòng thực hành.

Target ở root có ý nghĩa đặc biệt: Oracle yêu cầu root compartment là target để giám sát IAM policies. Nếu chỉ tạo các target ở compartment con, cần đánh giá khoảng trống giám sát cấp tenancy. [Oracle: Cloud Guard Concepts](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/cg-concepts.htm).

### 3.2. Chọn ranh giới có mục đích

Nên tách target khi nhóm cần hành vi khác nhau theo môi trường, chẳng hạn production yêu cầu người vận hành xác nhận còn phòng thực hành cho phép tự động sửa bucket thử nghiệm.

Không cần tạo target chỉ vì có thêm một VCN, Compute instance hay database. Hãy bắt đầu từ câu hỏi về phạm vi compartment, người chịu trách nhiệm và cấu hình recipe cần áp dụng.

Cần phân biệt hai thông tin khi dùng API hoặc công cụ hạ tầng:

- Compartment quản lý tài nguyên cấu hình Cloud Guard.
- Compartment tài nguyên mà target giám sát.

Không suy phạm vi giám sát chỉ từ nơi lưu recipe hoặc từ tên target. Hãy xem chi tiết target và cây compartment thực tế.

## 4. Detector recipes: phát hiện cấu hình và hoạt động

### 4.1. Hai nhóm cơ bản

| Nhóm | Trọng tâm | Cách đặt câu hỏi khi điều tra |
| --- | --- | --- |
| OCI Configuration Detector | Cấu hình tài nguyên có thể gây rủi ro | Tài nguyên hiện được cấu hình thế nào? |
| OCI Activity Detector | Hành động trên tài nguyên có thể gây rủi ro | Ai đã thực hiện hoạt động gì, vào thời điểm nào? |

Ví dụ, rule **Bucket is public** của Configuration Detector cảnh báo bucket public. Activity Detector có rule như **Bastion created**, giúp nhóm rà soát hoạt động tạo Bastion có được cho phép hay không. Một phát hiện cần được đối chiếu bối cảnh nghiệp vụ trước khi quyết định hành động. [Oracle: Detector Recipe Reference](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/detect-recipes.htm).

Quy trình tạo OCI target thông thường chọn một Configuration recipe và một Activity recipe. Oracle còn cung cấp lựa chọn bổ sung như Threat, Container Security Config và Instance Security; chúng cần được đánh giá theo nhu cầu và điều kiện sử dụng riêng. Không suy rằng gắn hai recipe cơ bản đã bao phủ mọi lớp workload. [Oracle: Creating an OCI Target](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/targets-create.htm).

### 4.2. Đọc một detector rule

Khi chuẩn bị đưa rule vào vận hành, lập bản ghi với các thông tin:

| Thông tin | Mục đích sử dụng |
| --- | --- |
| Tên và định danh rule | Tránh nhầm các rule có tên gần giống |
| Loại detector và tài nguyên | Xác định dữ liệu cần đối chiếu |
| Điều kiện phát hiện | Hiểu tình huống tạo problem |
| Risk level | Sắp xếp ưu tiên xử lý |
| Input settings, nếu có | Hiểu ngưỡng hoặc tham số đang áp dụng |
| Conditional group | Xác định các ngoại lệ và giới hạn phạm vi |
| Recipe và target đang sử dụng | Truy ra nơi cấu hình có hiệu lực |
| Chủ sở hữu xử lý | Chuyển problem đến đúng nhóm |

Đây là mẫu hồ sơ vận hành đề xuất, không phải schema API.

Risk level phục vụ ưu tiên điều tra. Khi một bucket được phép cung cấp tài liệu công khai, nhóm cần ghi nhận quyết định nghiệp vụ và điều kiện ngoại lệ; chỉ giảm mức cảnh báo không làm thay đổi cách bucket được truy cập.

## 5. Oracle-managed và user-managed recipes

Oracle cung cấp recipe quản lý sẵn. Khi cần thay đổi sâu hơn, người dùng clone để có user-managed recipe. Với detector, Oracle-managed recipe không cho người dùng tắt rule hoặc đổi risk level; user-managed recipe cho phép những điều chỉnh này. [Oracle: Editing Rule Settings in an OCI Detector Recipe](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/detect-recipes-modify-rules.htm).

| Nhu cầu | Cách triển khai phù hợp |
| --- | --- |
| Bắt đầu bằng baseline của Oracle | Xem và dùng Oracle-managed recipe |
| Đổi trạng thái hoặc risk level của detector rule | Clone detector recipe rồi chỉnh rule |
| Tắt một responder rule không phù hợp | Dùng user-managed responder recipe |
| Chỉ điều chỉnh phạm vi của một môi trường | Xem cấu hình rule trong target tương ứng |

Clone tạo bản cấu hình mới; phải gắn bản đó vào target cần sử dụng. Với detector, có thể clone từ Oracle-managed hoặc user-managed recipe trong cùng tenancy. [Oracle: Cloning an OCI Detector Recipe](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/detect-recipes-clone.htm).

Tương tự, clone responder recipe từ bộ gần với nhu cầu nhất rồi chỉnh cấu hình của bản mới. Đặt tên có mục đích, ví dụ `cg-lab-responder-v1`, và ghi người sở hữu cùng lý do thay đổi. [Oracle: Cloning an OCI Responder Recipe](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/respond-recipes-clone.htm).

User-managed recipe vẫn nhận các cập nhật rule từ nguồn Oracle-managed; rule mới được thêm vào bản clone ở trạng thái tắt theo tài liệu Oracle. Vì vậy, nhóm cần có lịch xem xét rule mới và quyết định bật chúng. [Oracle: Some Common Features](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/common.htm).

Một bản clone không phải bản đóng băng vĩnh viễn. Hồ sơ thay đổi nên ghi định danh recipe nguồn, các rule chủ động điều chỉnh và ngày rà soát gần nhất.

## 6. Sửa ở recipe level hay target level?

### 6.1. Phân biệt nơi sửa

Recipe có thể được tái sử dụng. Trước khi sửa, kiểm tra các target đang gắn recipe đó; một thay đổi baseline có thể ảnh hưởng nhiều môi trường.

Đối với detector rule trong OCI target thông thường, tài liệu thao tác của Oracle nêu rằng cấu hình sửa ở target level là **Conditional group**. Muốn đổi các thuộc tính khác, đi qua phần quản lý recipe thích hợp. Security Zone target có cơ chế riêng và không thuộc phạm vi lab này. [Oracle: Editing Detector Rule Settings in an OCI Target's Recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/targets-modify-rules-detect.htm).

Đối với responder, bật/tắt rule thực hiện ở recipe level và chỉ với user-managed recipe. Những thiết lập như chế độ thực thi và điều kiện áp dụng được chỉnh từ rule của recipe gắn vào target. [Oracle: Editing Responder Rule Settings in an OCI Target's Recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/targets-modify-rules-respond.htm).

Ví dụ quyết định:

| Muốn thay đổi | Điểm bắt đầu |
| --- | --- |
| Tắt detector rule trong baseline tùy chỉnh | Detector recipes → user-managed recipe → rule |
| Đổi risk level của detector rule | Detector recipes → user-managed recipe → rule |
| Đặt ngoại lệ cho detector trong phòng thực hành | Targets → target phòng thực hành → detector rule |
| Tắt responder rule trong bản tùy chỉnh | Responder recipes → user-managed recipe → rule |
| Chọn tự động hay cần xác nhận | Targets → target tương ứng → responder rule |

### 6.2. Điều kiện và ngoại lệ

Conditional group giới hạn nơi rule áp dụng. Các điều kiện kết hợp trong một nhóm dùng phép AND. Điều kiện ở recipe có thể làm mặc định khi gắn vào target mới; cần kiểm tra cấu hình riêng của target đã tồn tại. [Oracle: Some Common Features](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/common.htm).

Ví dụ chính sách nội bộ do bài học đề xuất:

~~~text
Phát hiện:
    Giữ rule phát hiện bucket public trong phạm vi phòng thực hành.

Khắc phục tự động:
    Chỉ áp dụng tại region được chọn cho lab
    VÀ chỉ cho tài nguyên có định danh đã được chấp thuận,
    nếu rule hỗ trợ tham số lọc tương ứng.
~~~

Đây là mô tả ý định, không phải biểu thức để dán vào API. Khi cấu hình, chọn đúng Parameter, Operator và Value mà rule hỗ trợ; nếu không biểu diễn được phạm vi mong muốn, giữ chế độ cần xác nhận.

Một ngoại lệ cần có chủ sở hữu, lý do, phạm vi và ngày hết hạn. Nếu dùng tag làm điều kiện, phân quyền gắn tag cũng cần được xem xét: người thay đổi được tag có thể làm thay đổi tài nguyên nào được responder xử lý.

## 7. Responder recipes: hành động và điều kiện thực thi

### 7.1. Chọn hành động theo tác động

Các ví dụ Oracle cung cấp gồm:

| Responder | Hành động | Điểm cần đánh giá trước khi dùng |
| --- | --- | --- |
| Make Bucket Private | Chuyển bucket public sang private | Ảnh hưởng người dùng truy cập nội dung công khai |
| Enable DB Backup | Bật sao lưu tự động cho database phù hợp | Cửa sổ sao lưu, thời gian lưu giữ và dung lượng |
| Stop Compute Instance | Dừng Compute instance | Khả năng phục vụ và phụ thuộc ứng dụng |
| Cloud Event | Phát chi tiết problem sang Events | Tuyến thông báo và người nhận |

Danh sách trên minh họa các responder có sẵn; phải kiểm tra rule áp dụng cho detector nào và tham số bắt buộc của chính rule đó. [Oracle: Responder Recipe Reference](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/respond-recipes-reference.htm).

Với hệ thống production, nên đánh giá tác động bằng một kịch bản cụ thể: nếu một instance bị dừng, dịch vụ có còn đủ replica và kết nối đến database có được duy trì không? Quyết định tự động hóa cần dựa trên khả năng phục hồi của ứng dụng.

### 7.2. Cần xác nhận và tự động

**Ask me before executing rule** dành quyền quyết định thực thi cho người vận hành. **Execute automatically** cho phép rule xử lý khi phù hợp cấu hình.

Khi cấu hình tự động cho responder rule khắc phục, Oracle yêu cầu xác nhận lựa chọn và có ít nhất một điều kiện. Hãy dùng điều kiện thể hiện phạm vi được chấp thuận, thay vì một điều kiện luôn đúng để bỏ giới hạn. [Oracle: Editing Responder Rule Settings in an OCI Target's Recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/targets-modify-rules-respond.htm).

Một quy tắc lựa chọn do bài học đề xuất:

~~~text
Chỉ cho phép tự động khi:
    Hiểu chính xác hành động
    VÀ xác định được phạm vi
    VÀ đã kiểm chứng bằng tài nguyên thử nghiệm
    VÀ có người chịu trách nhiệm
    VÀ có cách xử lý khi hành động gây tác động ngoài dự kiến.
~~~

Nếu một điều kiện chưa đạt, tiếp tục vận hành bằng chế độ cần xác nhận để tích lũy bằng chứng.

### 7.3. Quyền quản trị và quyền của dịch vụ

Cần tách ba lớp quyền:

1. **Người vận hành quản lý Cloud Guard:** xem problem, sửa recipe, cấu hình target hoặc thực hiện các tác vụ được giao.
2. **Dịch vụ Cloud Guard quan sát:** các policy tiền đề cho phép dịch vụ thu thập thông tin cần thiết.
3. **Dịch vụ Cloud Guard khắc phục:** các policy bổ sung cho hành động làm thay đổi tài nguyên.

Ví dụ quyền đọc dành cho nhóm kiểm toán:

~~~text
Allow group CloudGuardReaders to read cloud-guard-family in tenancy
Allow group CloudGuardReaders to read compartments in tenancy
~~~

Hai statement này minh họa quyền xem dữ liệu và cấu hình. Tên nhóm cần tồn tại trong tenancy; điều chỉnh cú pháp identity domain nếu nhóm thuộc domain khác. [Oracle: Prerequisites](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/prerequisites.htm), [Oracle: Cloud Guard Policies](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/policies.htm).

Với `Make Bucket Private`, ví dụ quyền dịch vụ được giới hạn trong compartment lab là:

~~~text
Allow service cloudguard to manage buckets in compartment SecurityLab
~~~

`SecurityLab` là tên minh họa và cần thay bằng compartment thực tế. Chỉ thêm policy khắc phục tương ứng với hành động đã chọn; kiểm tra danh sách **Required policy statements** của rule. Người có quyền cấu hình recipe không tự động đồng nghĩa dịch vụ đã có quyền sửa bucket. [Oracle: Policy Statements for OCI Responders](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/respond-recipes-about.htm#PolicyStatements).

## 8. Reporting region và cấu hình ban đầu

Reporting region là điểm cấu hình quan trọng của Cloud Guard, không mặc nhiên trùng OCI home region. Các thao tác tạo, sửa và xóa Cloud Guard cần gửi đến reporting region; thao tác đọc được hỗ trợ từ các region khác. [Oracle: Cloud Guard CLI](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/cloud-guard.html).

Trước lab, xác nhận:

- Tenancy đã có Cloud Guard hoạt động và các policy tiền đề cần thiết.
- Đã ghi đúng reporting region trong cấu hình công cụ.
- Tài khoản thực hành có quyền với target và recipe cần thao tác.
- Đã xác định target hiện đang quản lý nhánh compartment của lab.
- Phòng thực hành không chứa dữ liệu nghiệp vụ hoặc tài nguyên dùng chung.

Tài liệu khởi tạo Oracle nêu rằng đổi reporting region cần tắt rồi bật lại Cloud Guard, và việc tắt làm mất các tùy chỉnh cùng lịch sử problem hiện có. Vì thế, không dùng thao tác này để thử sửa lỗi cấu hình hoặc thông báo trong môi trường đang vận hành. [Oracle: Getting Started with Cloud Guard](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/part-start.htm).

Các thay đổi tài nguyên và việc xuất hiện problem có thể không đồng thời. Trong lab, ghi thời điểm thay đổi, chờ dữ liệu được cập nhật và kiểm tra chuỗi cấu hình trước khi kết luận detector không hoạt động.

## 9. Thiết kế baseline cho các môi trường

Bảng sau là phương án minh họa, không phải mặc định của Oracle:

| Target | Phạm vi | Detector baseline | Cách xử lý ban đầu |
| --- | --- | --- | --- |
| `cg-root` | Root và các nhánh chưa có target riêng | Baseline cấp tenancy | Điều tra, có xác nhận |
| `cg-production` | Production | Baseline được nhóm bảo mật kiểm soát | Có xác nhận cho thay đổi tài nguyên |
| `cg-development` | Development, trừ nhánh lab riêng | Baseline development | Thông báo và xử lý theo chủ sở hữu |
| `cg-lab` | SecurityLab | Bản clone phục vụ lab | Ban đầu có xác nhận; sau đó thử tự động có điều kiện |

Bản thiết kế nên ghi rõ mỗi target dùng recipe nào. Nếu hai môi trường cần trạng thái bật/tắt rule khác nhau, chọn các bản user-managed phù hợp; chỉ tách tên target mà vẫn dùng chung baseline chưa chắc tạo được sự khác biệt mong muốn.

Khi thay recipe trên OCI target, lưu ý mỗi loại chỉ có một recipe được gắn tại một thời điểm; để thêm bản thay thế cùng loại có thể cần gỡ bản đang gắn. Lập trình tự thay đổi và xác minh liên kết sau thao tác để hạn chế khoảng trống giám sát. [Oracle: Editing an OCI Target and Its Attached Recipes](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/targets-modify.htm).

## 10. Thực hành: phát hiện và xử lý bucket public

Lab này sử dụng OCI Console và một bucket rỗng trong compartment thử nghiệm. Các thao tác dưới đây là hướng dẫn để người học thực hiện; không phải kết quả đã chạy trên một tenancy.

### Bước 1 — Chuẩn bị phạm vi và bảng ghi nhận

Chọn compartment lab có quyền thao tác, ví dụ `SecurityLab`. Nếu compartment thuộc target khác, ghi lại cấu hình hiện tại trước khi tạo target riêng.

Lập bảng theo dõi:

| Trường | Giá trị cần ghi |
| --- | --- |
| Reporting region | Region thật của Cloud Guard |
| Compartment lab | Tên và OCID |
| Target | Tên và OCID |
| Configuration, Activity recipes | OCID nguồn và bản clone nếu có |
| Responder recipe | OCID và chế độ rule khắc phục |
| Bucket | Tên, OCID, region |
| Người chịu trách nhiệm | Người thực hành hoặc người trực xử lý |

Không đặt secret, thông tin cá nhân hoặc dữ liệu khách hàng trong tên tài nguyên và mô tả.

### Bước 2 — Clone và gắn recipe

Trong **Cloud Guard → Recipes**, tạo các bản phục vụ lab:

- Configuration recipe: `cg-lab-config-v1`.
- Activity recipe: `cg-lab-activity-v1` nếu cần baseline riêng.
- Responder recipe: `cg-lab-responder-v1`.

Trong **Configuration → Targets**, tạo hoặc chỉnh target `cg-lab` cho compartment đã chọn. Gắn Configuration recipe và Activity recipe phù hợp, rồi gắn responder recipe lab.

Đối với Configuration recipe, xác nhận rule **Bucket is public** đang bật và kiểm tra điều kiện của rule trong target. Đối với responder lab, giữ **Make Bucket Private** ở chế độ cần xác nhận. Rà soát các rule làm thay đổi tài nguyên khác trước khi tiếp tục.

Mốc hoàn thành bước này là thấy đúng OCID recipe trong chi tiết target. Việc recipe xuất hiện trong danh sách toàn cục chưa đủ để chứng minh nó đang được dùng.

### Bước 3 — Tạo tình huống phát hiện có kiểm soát

Tạo một bucket rỗng trong compartment và region đã ghi. Xác nhận bucket đang private, sau đó đổi visibility sang public để tạo tình huống thử nghiệm. Không tải dữ liệu thật vào bucket.

Trong Cloud Guard, tìm problem tương ứng với bucket. Đối chiếu:

- Resource OCID và region.
- Target có hiệu lực.
- Detector và rule.
- Thời điểm phát hiện, risk level và khuyến nghị.

Ghi thời điểm chuyển visibility và thời điểm quan sát thấy problem. Nếu chưa thấy, kiểm tra bộ lọc, phạm vi target, recipe gắn vào target, trạng thái rule và policy tiền đề.

### Bước 4 — Thực thi responder sau khi xác nhận

Mở problem hoặc **Responder activity**, xem hành động **Make Bucket Private** đang chờ. Đọc tác động và xác nhận thực thi cho bucket thử nghiệm.

Nếu cần, bổ sung policy dịch vụ đúng phạm vi. Sau khi thực thi, kiểm tra trạng thái responder và mở Object Storage để xác nhận visibility thực tế của bucket đã là private.

Trang Responder activity có thể hiển thị các trạng thái như **Awaiting confirmation**, **Failed**, **Skipped** và **Succeeded**. Khi thất bại, xem chi tiết để phân biệt thiếu quyền với tài nguyên không còn khả dụng. [Oracle: Listing Responder Rule Actions and Getting the Details](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/respond-dash-work.htm).

Bằng chứng của lab phải gồm cả hoạt động responder và trạng thái bucket; chỉ đổi trạng thái hồ sơ problem không chứng minh tài nguyên đã được sửa.

### Bước 5 — Thử tự động hóa trong phạm vi lab

Sau khi kiểm chứng chế độ có xác nhận:

1. Mở rule **Make Bucket Private** từ responder recipe trong target lab.
2. Chọn tự động thực thi và xác nhận lựa chọn.
3. Đặt conditional group thể hiện phạm vi lab bằng tham số rule hỗ trợ.
4. Kiểm tra policy khắc phục vẫn giới hạn đúng compartment.
5. Dùng bucket thử nghiệm khác để tạo một phát hiện mới.
6. Đối chiếu hành động tự động và visibility cuối cùng.

Dùng bucket mới giúp tách lần thử tự động khỏi hồ sơ problem của lần trước. Không giả định thay trigger sẽ luôn khiến một problem cũ được chạy lại ngay.

Lưu cùng nhau điều kiện áp dụng, OCID bucket, thời điểm phát hiện và kết quả responder. Nếu chưa xác minh được khả năng giới hạn phạm vi, quay về chế độ cần xác nhận trước khi tiếp tục.

### Bước 6 — Hoàn nguyên và kết thúc lab

Chuyển các bucket thử nghiệm về private, xóa tài nguyên lab không cần giữ và đưa rule về chế độ đã thống nhất với người quản lý môi trường.

Rà soát các policy chỉ được thêm cho lab; thu hồi khi không còn nhu cầu và sau khi kiểm tra chúng không phục vụ quy trình khác. Nếu lab đã thay cấu hình target hiện có, khôi phục theo bản ghi trước thay đổi và xác nhận phạm vi giám sát sau cùng.

Không tắt Cloud Guard toàn tenancy chỉ để dọn một bài thực hành.

## 11. Chuyển tiếp thông báo qua Cloud Event, Events và Notifications

Cloud Event responder phát chi tiết problem sang Events. Để nhận thông báo, cần gắn responder recipe vào target và kiểm tra Cloud Event rule đang bật, thực thi tự động. Các dịch vụ Events và Notifications cho luồng này được cấu hình tại reporting region. [Oracle: Configuring Notifications](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/export-notifs-config.htm).

~~~text
Problem
  → Cloud Event responder
  → Events rule tại reporting region
  → Notifications topic
  → Subscription đã được xác nhận
~~~

Trong lab, chọn event type `com.oraclecloud.cloudguard.problemdetected` để thử tuyến thông báo. Gửi đến một Notifications topic của nhóm thực hành và hoàn tất xác nhận subscription nếu dùng email. [Oracle: Configuring Notifications](https://docs.oracle.com/en-us/iaas/Content/cloud-guard/using/export-notifs-config.htm).

Sau đó thử nghiệm theo từng chặng: có problem, có responder phù hợp, Events rule khớp và subscription nhận được thông báo.

Thông báo phát hiện và thông báo sau khắc phục phục vụ hai mục đích khác nhau. Thiết kế thông điệp nội bộ nên ghi rõ đây là yêu cầu điều tra hay bằng chứng hành động đã hoàn thành.

## 12. Đọc cấu hình bằng OCI CLI trên PowerShell

Các lệnh dưới đây chỉ truy vấn. Cần cài OCI CLI, cấu hình xác thực và thay các chuỗi `<...>` bằng OCID, region thực tế.

### 12.1. Liệt kê target trong cây tenancy

~~~powershell
$tenancyOcid = '<TENANCY_OCID>'
$reportingRegion = '<CLOUD_GUARD_REPORTING_REGION>'

oci cloud-guard target list --compartment-id $tenancyOcid --compartment-id-in-subtree true --access-level ACCESSIBLE --all --region $reportingRegion
~~~

`--compartment-id-in-subtree true` yêu cầu xét cây compartment; `--all` lấy hết các trang. Với `ACCESSIBLE`, kết quả phụ thuộc phạm vi quyền của người gọi, nên danh sách ít phần tử chưa đủ để kết luận các target khác không tồn tại. [Oracle CLI: target list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/cloud-guard/target/list.html).

### 12.2. Kiểm tra recipe thực sự gắn vào target

~~~powershell
$targetOcid = '<TARGET_OCID>'
$targetCompartmentOcid = '<COMPARTMENT_OCID_CUA_TARGET>'

oci cloud-guard target-detector-recipe list --compartment-id $targetCompartmentOcid --target-id $targetOcid --all --region $reportingRegion

oci cloud-guard target-responder-recipe list --compartment-id $targetCompartmentOcid --target-id $targetOcid --all --region $reportingRegion
~~~

Dùng compartment chứa target theo thông tin quản lý của nó. Hai truy vấn giúp đối chiếu liên kết detector/responder thay vì chỉ tìm recipe theo tên. [Oracle CLI: target-detector-recipe list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/cloud-guard/target-detector-recipe/list.html), [Oracle CLI: target-responder-recipe list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/cloud-guard/target-responder-recipe/list.html).

### 12.3. Lấy chi tiết problem

~~~powershell
$problemOcid = '<PROBLEM_OCID>'

oci cloud-guard problem get --problem-id $problemOcid --region $reportingRegion
~~~

Lệnh lấy problem theo định danh, hữu ích khi chuyển giao điều tra giữa các nhóm. Khi lưu kết quả phục vụ kiểm toán, kiểm soát người đọc vì chi tiết tài nguyên có thể chứa thông tin nội bộ. [Oracle CLI: problem get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/cloud-guard/problem/get.html).

Không đưa lệnh ghi vào lịch tự động chỉ vì lệnh đọc đã chạy thành công. Một quy trình sửa recipe hoặc target cần kiểm tra định danh, phạm vi tác động và kế hoạch khôi phục riêng.

## 13. Vận hành, kiểm toán và theo dõi hiệu quả

### 13.1. Hồ sơ thay đổi

Với mỗi thay đổi Cloud Guard, nên lưu:

| Nhóm bằng chứng | Nội dung |
| --- | --- |
| Phạm vi | Target OCID, compartment tree và môi trường |
| Baseline | Recipe OCID, recipe nguồn, rule đã sửa |
| Ngoại lệ | Điều kiện, lý do, người duyệt và ngày hết hạn |
| Quyền | Policy được thêm, mục đích và phạm vi |
| Thực thi | Problem OCID, responder, thời điểm và kết quả |
| Xác minh | Trạng thái tài nguyên sau hành động |
| Khôi phục | Cấu hình trước thay đổi và người chịu trách nhiệm |

Đây là hồ sơ đề xuất cho tổ chức. Khi điều tra, đối chiếu với OCI Audit và hệ thống quản lý thay đổi để xác định ai đã thay cấu hình hoặc tài nguyên và thay đổi đó có được chấp thuận không.

Không dùng một ảnh chụp màn hình tổng quan làm bằng chứng duy nhất cho phạm vi giám sát. Cần thấy target, recipe và rule liên quan đến chính tài nguyên được kiểm tra.

### 13.2. Chỉ số do nhóm tự xây dựng

Các chỉ số vận hành có thể gồm:

- Số compartment quan trọng đã có target và baseline được xác nhận.
- Thời gian từ khi problem xuất hiện đến khi được tiếp nhận.
- Thời gian từ tiếp nhận đến khi tài nguyên được khắc phục.
- Tỷ lệ responder thành công trên các lần thực thi phù hợp.
- Số ngoại lệ quá hạn.
- Số rule mới trong bản clone chưa được xem xét.
- Số problem tái diễn do cấu hình hạ tầng được triển khai lại.

Khi tính tỷ lệ, ghi rõ mẫu số và cửa sổ thời gian. Ví dụ, không trộn các lần chờ phê duyệt với các lần đã thực thi rồi thất bại.

Nếu bucket thường xuyên bị đổi lại sang public sau khi responder sửa, kiểm tra nguồn tạo cấu hình như Terraform hoặc quy trình triển khai ứng dụng. Sửa nguồn cấu hình giúp tránh vòng lặp phát hiện và khắc phục.

## 14. Chẩn đoán các tình huống thường gặp

Bảng này là trình tự điều tra đề xuất:

| Hiện tượng | Điểm cần kiểm tra trước | Hành động tiếp theo |
| --- | --- | --- |
| Đã clone nhưng hành vi không đổi | Recipe OCID đang gắn trong target | Gắn đúng bản và kiểm tra cấu hình có hiệu lực |
| Compartment con dùng baseline khác dự kiến | Có target riêng trong nhánh không | Đối chiếu lại cây target |
| Không thấy problem của bucket | Scope, bộ lọc, trạng thái rule và thời điểm thay đổi | Kiểm tra policy tiền đề và chờ dữ liệu cập nhật |
| Không có hành động khắc phục mong muốn | Responder recipe, rule và khả năng áp dụng | Đối chiếu detector–responder trong tài liệu rule |
| Responder chờ xác nhận | Rule trigger | Người có trách nhiệm quyết định thực thi |
| Responder thất bại | Chi tiết execution và quyền dịch vụ | Sửa đúng nguyên nhân, tránh mở quyền toàn tenancy để thử |
| Không nhận được email | Cloud Event, reporting region, Events rule và subscription | Kiểm tra từng chặng |
| Quá nhiều phát hiện | Ngữ cảnh tài nguyên và ngoại lệ hiện có | Thu hẹp ngoại lệ có thời hạn |
| Sửa baseline ảnh hưởng môi trường khác | Các target dùng chung recipe | Khôi phục và tách baseline nếu cần |
| Ít kết quả CLI hơn Console của quản trị viên | Quyền và tham số truy vấn subtree | Đối chiếu bằng người có quyền phù hợp |

Khi sự cố chưa rõ, giữ lại problem và lịch sử thực thi trước khi sửa tiếp. Việc thay đồng thời target, rule, policy và thông báo làm khó xác định nguyên nhân.

## 15. Chi phí và tính sẵn sàng trong thiết kế phản ứng

Trong phương án thực hành, cần tính tài nguyên sử dụng kèm theo: bucket thử nghiệm, dữ liệu và log lưu giữ, tuyến thông báo, cùng các dịch vụ phát sinh từ hành động khắc phục. Kiểm tra bảng giá và Cost Analysis theo tài khoản đang dùng trước khi mở rộng lab.

Với responder bật sao lưu database, nhóm cần thống nhất cửa sổ sao lưu và thời gian lưu giữ với người quản trị cơ sở dữ liệu. Với hành động dừng instance hoặc đổi bucket sang private, kiểm tra luồng truy cập và yêu cầu phục vụ trước khi cho phép tự động.

Một lộ trình triển khai do bài học đề xuất là:

1. Bắt đầu bằng phát hiện và chuyển thông báo đến người chịu trách nhiệm.
2. Thực hiện khắc phục có xác nhận trên môi trường thử nghiệm.
3. Đo kết quả và ghi nhận những trường hợp ngoại lệ.
4. Bật tự động cho hành động, target và điều kiện đã kiểm chứng.
5. Mở rộng từng phạm vi và tiếp tục rà soát recipe cùng quyền dịch vụ.

Kết quả cần đạt là một cấu hình có thể giải thích được: mỗi tài nguyên thuộc target nào, rule nào phát hiện vấn đề, ai quyết định xử lý và bằng chứng nào cho thấy trạng thái sau khắc phục.
