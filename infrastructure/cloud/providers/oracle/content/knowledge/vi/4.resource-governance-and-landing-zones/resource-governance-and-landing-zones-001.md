# Thiết kế compartment cho tổ chức, dự án và môi trường

Một công ty triển khai ứng dụng bán hàng trên Oracle Cloud Infrastructure (OCI). Nhóm phát triển cần tự tạo máy ảo thử nghiệm; nhóm vận hành chịu trách nhiệm production; nhóm nền tảng quản lý mạng dùng chung; bộ phận tài chính cần biết chi phí của từng sản phẩm. Nếu mọi tài nguyên cùng nằm ở root compartment và mọi nhóm đều có quyền quản trị rộng, một thay đổi thử nghiệm có thể ảnh hưởng đến hệ thống đang bán hàng.

Compartment giúp chuyển những yêu cầu quản trị đó thành cách tổ chức tài nguyên và phạm vi cấp quyền cụ thể. Thiết kế tốt phải giải thích được ba điều: tài nguyên thuộc trách nhiệm của ai, ai được làm gì và thay đổi ở đâu sẽ ảnh hưởng đến những môi trường nào.

Bài học thuộc chương **Tổ chức tài nguyên và landing zone** trong phạm vi **CLOUD_PROVIDERS_ORACLE**. Các ví dụ tập trung vào việc đặt tài nguyên Compute, VCN, lưu trữ và dịch vụ cơ sở dữ liệu Oracle vào một cấu trúc OCI có thể phân quyền, theo dõi chi phí và tự động hóa. Compartment là một phần của landing zone; yêu cầu về giám sát, kết nối và tính sẵn sàng vẫn cần được thiết kế cùng cấu trúc này.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Chọn trục phân cấp phù hợp giữa đơn vị tổ chức, dự án và môi trường.
- Phân biệt phạm vi quản trị của compartment với ranh giới mạng và vị trí triển khai.
- Nhận ra quyền IAM có thể lan xuống các compartment con.
- Tách tài nguyên dùng chung khỏi tài nguyên do từng nhóm sản phẩm quản lý.
- Mô tả quyền sở hữu, chi phí và vòng đời cho mỗi compartment trước khi triển khai.
- Tạo một cây compartment thực hành và xác minh nó bằng OCI CLI.

Giả định người học đã biết tenancy là phạm vi tài khoản OCI của tổ chức, IAM policy là quy tắc cấp hoặc kiểm soát quyền truy cập, còn OCID là định danh của một tài nguyên OCI. Khi gặp OCID trong ví dụ, cần thay bằng định danh thật của môi trường thực hành.

## 2. Compartment biểu diễn điều gì?

Compartment là một nhóm tài nguyên theo logic trong tenancy. Khi tạo tài nguyên có hỗ trợ compartment, người triển khai chọn compartment chứa nó. Trong cây phân cấp, một compartment con có một compartment cha; nó không đồng thời nằm dưới cả nhánh dự án và nhánh phòng ban. Vì vậy, cây cần có một trục quản trị chính, còn những chiều phân loại khác được thể hiện bằng tag, báo cáo hoặc tài liệu vận hành.

| Khái niệm | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| Tenancy | Tổ chức đang quản trị trong phạm vi tài khoản OCI nào? | Tenancy của công ty |
| Compartment | Tài nguyên thuộc phạm vi quản trị nào? | `shop/prod` |
| Region | Tài nguyên được triển khai ở khu vực OCI nào? | Region chính và region dự phòng |
| VCN, subnet và quy tắc mạng | Tài nguyên kết nối với nhau như thế nào? | Mạng ứng dụng và subnet cơ sở dữ liệu |
| Tag | Tài nguyên được phân loại theo thuộc tính nào? | Chủ sở hữu, trung tâm chi phí, mức nhạy cảm |

Compartment có phạm vi toàn cục, trong khi nhiều tài nguyên như Compute instance và VCN thuộc một region. Một compartment có thể chứa tài nguyên ở nhiều region; bộ lọc region trên Console vẫn quyết định những tài nguyên hiển thị trong trang dịch vụ. Vì vậy, danh sách instance rỗng chưa đủ để kết luận compartment không còn tài nguyên. Xem [Working in Regions](https://docs.oracle.com/en-us/iaas/Content/GSG/Concepts/working-with-regions.htm).

Hai hệ quả thiết kế cần nhớ:

1. **Tách compartment không tự tạo sự cô lập mạng.** Hai máy ảo ở hai compartment khác nhau vẫn có thể giao tiếp nếu cấu hình kết nối và quy tắc mạng cho phép.
2. **Tách compartment không tự tạo tính sẵn sàng cao.** Một ứng dụng chỉ có một instance vẫn có điểm lỗi đơn dù instance nằm trong compartment tên `prod`. Khả năng chịu lỗi phụ thuộc kiến trúc triển khai, dữ liệu và quy trình phục hồi.

Nên giữ root compartment cho những thành phần thực sự cần phạm vi tenancy và phần quản trị nền tảng phù hợp. Workload nghiệp vụ nên có compartment riêng để người vận hành không phải xin quyền rộng ở root chỉ để thực hiện công việc cục bộ.

## 3. Bắt đầu từ yêu cầu quản trị

Không nên bắt đầu bằng việc vẽ lại toàn bộ sơ đồ nhân sự thành cây compartment. Phòng ban có thể đổi tên hoặc sáp nhập, trong khi hệ thống production vẫn cần giữ trách nhiệm vận hành và chính sách bảo vệ ổn định.

Trước khi tạo cây, hãy trả lời các câu hỏi sau cho từng nhóm tài nguyên:

| Câu hỏi thiết kế | Ảnh hưởng đến cấu trúc |
| --- | --- |
| Ai chịu trách nhiệm cuối cùng khi hệ thống gặp sự cố? | Xác định chủ sở hữu của nhánh hoặc compartment lá |
| Nhóm phát triển và vận hành có quyền khác nhau không? | Cân nhắc tách `dev`, `staging`, `prod` |
| Hai sản phẩm có lịch phát hành và vòng đời độc lập không? | Cân nhắc compartment riêng cho từng sản phẩm |
| Mạng, kết nối và khóa mã hóa do đội nào quản lý? | Xác định tài nguyên dùng chung và quyền sử dụng chéo |
| Có yêu cầu dữ liệu nhạy cảm khác biệt không? | Cân nhắc nhánh riêng và bổ sung kiểm soát dữ liệu |
| Chi phí cần được giải trình theo dự án hay đơn vị? | Chọn trục chính và thiết kế tag bổ sung |
| Ai được tạo compartment con và thay đổi policy? | Quyết định phạm vi ủy quyền quản trị |
| Khi dự án kết thúc, ai thu hồi quyền và xử lý dữ liệu? | Xác định vòng đời, người duyệt và quy trình kết thúc |

Ví dụ, hai nhóm cùng thuộc phòng Công nghệ nhưng có hợp đồng hỗ trợ, dữ liệu và ngân sách khác nhau có thể cần hai nhánh dự án riêng. Ngược lại, ba nhóm phát triển cùng vận hành một sản phẩm có thể dùng chung nhánh sản phẩm, phân biệt vai trò bằng IAM thay vì tạo compartment cho từng nhóm.

Một tiêu chí thực dụng là: **nếu hai tập tài nguyên cần khác nhau về quyền quản trị, chủ sở hữu hoặc vòng đời, hãy xem xét tách compartment; nếu chỉ khác thuộc tính báo cáo, hãy xem xét tag trước.** Đây là nguyên tắc lựa chọn thiết kế, không phải quy tắc bắt buộc của OCI.

## 4. Chọn thứ tự tổ chức, dự án và môi trường

### 4.1. Ba mô hình thường gặp

| Mô hình | Điểm mạnh | Điểm cần cân nhắc |
| --- | --- | --- |
| Đơn vị → dự án → môi trường | Giao trách nhiệm và tổng hợp theo đơn vị rõ ràng | Dễ bị xáo trộn khi tái cơ cấu nếu bám quá sát sơ đồ nhân sự |
| Dự án → môi trường | Thuận tiện khi một nhóm sở hữu trọn vòng đời sản phẩm | Nhóm vận hành nhiều hệ thống production cần policy trên nhiều nhánh |
| Môi trường → dự án | Thuận tiện khi production do một bộ phận vận hành tập trung | Một nhóm sản phẩm phải nhận quyền ở nhiều nhánh để quản lý đủ môi trường |

Không có một thứ tự tối ưu cho mọi tổ chức. Chọn trục cấp trên dựa trên nơi cần ủy quyền lâu dài nhất. Sau đó kiểm tra xem quyền ở cấp đó có vô tình bao trùm các môi trường cần bảo vệ riêng hay không.

Ví dụ, mô hình `workloads/shop/dev` và `workloads/shop/prod` phù hợp khi Shop là một sản phẩm ổn định, nhưng không có nghĩa nhóm phát triển phải được quyền quản trị ở `shop`. Quyền có thể được cấp riêng ở từng compartment môi trường.

### 4.2. Cây tham chiếu cho hai sản phẩm

Giả sử tổ chức có sản phẩm Shop và CRM, một nhóm nền tảng dùng chung và một nhóm an toàn thông tin. Có thể dùng cấu trúc sau:

```text
tenancy (root)
└── org
    ├── security
    ├── shared
    │   ├── shared-nonprod
    │   └── shared-prod
    ├── workloads
    │   ├── shop
    │   │   ├── dev
    │   │   ├── staging
    │   │   └── prod
    │   └── crm
    │       ├── dev
    │       └── prod
    └── sandbox
```

Vai trò của từng nhánh trong thiết kế minh họa:

- `org` là điểm gom phạm vi quản trị của tổ chức trong tenancy.
- `security` dành cho tài nguyên bảo mật hoặc thu thập log do nhóm an toàn thông tin sở hữu, theo khả năng từng dịch vụ.
- `shared-nonprod` và `shared-prod` chứa thành phần nền tảng dùng chung nhưng có mức rủi ro và quy trình thay đổi khác nhau.
- `workloads` gom tài nguyên nghiệp vụ. Các nhánh `shop` và `crm` là điểm quản lý sản phẩm; các compartment môi trường bên dưới chứa tài nguyên tương ứng.
- `sandbox` dành cho thử nghiệm có người phụ trách, thời hạn và giới hạn sử dụng rõ ràng.

Các nút như `workloads` hoặc `shop` có thể chủ yếu dùng để tổ chức cây, còn workload được đặt tại compartment môi trường. Đây là quy ước vận hành được lựa chọn để giảm nhầm lẫn; OCI không bắt buộc nút cha phải trống.

Trong ví dụ này, đường dẫn có dấu `/` là cách mô tả cho người đọc. Khi viết IAM policy dùng đường dẫn compartment, ví dụ bên dưới sử dụng dấu `:` theo cú pháp OCI.

### 4.3. Khi nào cần tách thêm tầng?

Ban đầu, `shop/prod` có thể chứa instance, bucket và tài nguyên cơ sở dữ liệu của cùng ứng dụng. Chỉ nên thêm compartment như `application` và `database` khi có sự khác biệt đáng kể về quyền sở hữu hoặc kiểm soát.

Ví dụ, nếu DBA quản lý cơ sở dữ liệu và đội ứng dụng không được thay đổi cấu hình cơ sở dữ liệu, việc tách có thể làm phạm vi cấp quyền rõ hơn. Tuy nhiên, mỗi lần chia nhỏ đều làm tăng số policy, phụ thuộc chéo và thao tác kiểm kê. Tách từng loại tài nguyên thành một compartment riêng ngay từ đầu thường gây phức tạp mà chưa giải quyết yêu cầu cụ thể.

Cũng không cần nhân bản toàn bộ cây chỉ vì triển khai thêm region. Chỉ thêm trục region khi nó giải quyết yêu cầu quản trị thực tế, chẳng hạn hai đội vận hành có trách nhiệm khu vực độc lập. Nếu yêu cầu chỉ là triển khai dự phòng, hãy thiết kế khả năng phục hồi cùng kiến trúc dịch vụ trước.

## 5. Thiết kế cây cùng với quyền IAM

### 5.1. Quyền ở cha có thể tác động đến con

Một policy cấp quyền trên compartment cha có thể áp dụng xuống compartment con. Với cây tham chiếu, statement sau có phạm vi rộng hơn nhu cầu của một lập trình viên chỉ làm việc ở `dev`:

```text
Allow group 'Default'/'ShopDevelopers' to manage all-resources in compartment org:workloads:shop
```

Phạm vi đó bao gồm các môi trường nằm dưới `shop`, trong đó có `prod`. Chỉ bổ sung một allow policy hẹp hơn ở `dev` không thu hồi quyền đã cấp bởi allow policy rộng ở cha. Cần rà soát các grant ở cấp trên và các nhóm mà người dùng tham gia. Xem [Policy Inheritance](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Inheritance.htm).

OCI có **IAM deny policies** dưới dạng tính năng cần bật chủ động. Khi được bật, deny có thể chặn quyền đã được allow. Vì vậy, không nên khẳng định OCI chỉ có allow hoặc compartment con luôn có thể tự phủ định quyền ở cha. Các ví dụ trong bài dùng allow và không giả định tenancy đã bật deny; nếu tổ chức dùng deny, phải đánh giá thêm chúng khi xác minh quyền hiệu lực. Xem [Deny Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/denypolicies.htm).

### 5.2. Cấp quyền theo môi trường và công việc

Một ma trận trách nhiệm ban đầu có thể như sau:

| Nhóm minh họa | Phạm vi chính | Công việc dự kiến |
| --- | --- | --- |
| `ShopDevOperators` | `shop/dev` | Quản lý các tài nguyên phát triển được giao |
| `ShopStagingOperators` | `shop/staging` | Triển khai và vận hành kiểm thử tích hợp |
| `ShopProdOperators` | `shop/prod` | Vận hành production theo quy trình thay đổi |
| `PlatformNetworkAdmins` | Các compartment mạng dùng chung được giao | Quản lý kết nối và cấu hình mạng nền tảng |
| `SecurityReviewers` | Các phạm vi cần kiểm tra | Đọc cấu hình và bằng chứng cần thiết cho kiểm tra |

Không thể chuyển trực tiếp một dòng “quản lý tài nguyên” thành `manage all-resources` cho mọi nhóm. Cần phân tích nhóm đó phải gọi API nào, trên loại tài nguyên nào và có phụ thuộc gì ở compartment khác.

Ví dụ dưới đây minh họa các grant cho Compute, volume và mạng trong **riêng môi trường dev**. Policy được giả định gắn tại root; `Default` là tên identity domain của ví dụ và phải thay nếu tenancy dùng domain khác.

```text
Allow group 'Default'/'ShopDevOperators' to manage instance-family in compartment org:workloads:shop:dev
Allow group 'Default'/'ShopDevOperators' to manage volume-family in compartment org:workloads:shop:dev
Allow group 'Default'/'ShopDevOperators' to use virtual-network-family in compartment org:workloads:shop:dev
```

Đây là ví dụ về phạm vi compartment, chưa phải bộ quyền hoàn chỉnh cho mọi cách khởi tạo Compute. Việc dùng image tùy chỉnh, khóa mã hóa, defined tag hoặc tài nguyên ở compartment khác có thể cần quyền bổ sung. `use virtual-network-family` cũng bao phủ nhiều thao tác mạng; triển khai thực tế cần thu hẹp theo các API và loại tài nguyên mà nhóm thực sự sử dụng.

Trong policy, dấu `:` nối các cấp compartment tương đối với nơi policy được gắn. Có thể dùng `in compartment id <COMPARTMENT_OCID>` để định danh trực tiếp compartment đích. Không thêm tên tenancy vào đường dẫn như một compartment con. Xem [Policy Syntax](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policysyntax.htm).

### 5.3. Nơi đặt policy cũng là quyết định quản trị

Cần phân biệt:

- **Nơi gắn policy:** đối tượng policy được lưu và quản lý ở root hay một compartment cụ thể.
- **Phạm vi của statement:** tài nguyên mà quy tắc trong policy cho phép truy cập.

Hai yếu tố này liên quan nhưng không đồng nhất. Đặt policy ở root không có nghĩa mọi statement đều cấp quyền toàn tenancy; ví dụ phía trên vẫn chỉ định compartment dev. Vị trí gắn policy còn ảnh hưởng đến việc ai được sửa hoặc xóa policy. Xem [Working with Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/Working_with_Compartments.htm).

Với production, một lựa chọn hợp lý là để nhóm nền tảng hoặc quản trị IAM sở hữu các policy cấp quyền vận hành, còn nhóm sản phẩm nhận quyền trên tài nguyên được giao. Nếu ủy quyền quản lý policy cho nhóm sản phẩm, phải đánh giá khả năng họ thay đổi quyền trong phạm vi được ủy quyền.

Không cấp quyền rộng tại `workloads` chỉ để giảm số dòng policy, vì thao tác đó có thể mở quyền sang mọi sản phẩm con. Sự ngắn gọn của policy cần phục vụ mô hình quyền đã thống nhất.

## 6. Quản lý tài nguyên dùng chung và phụ thuộc chéo

Tài nguyên dùng chung thường gồm mạng trung tâm, kết nối với hệ thống tại chỗ hoặc thành phần vận hành do một đội nền tảng quản lý. Đưa chúng vào `shared` giúp thể hiện trách nhiệm, nhưng chưa xác định được nhóm workload được sử dụng chúng bằng cách nào.

Ví dụ, instance của Shop ở `shop/dev` có thể cần sử dụng một subnet được quản lý ở `shared-nonprod`. Đội triển khai phải xác định quyền cần thiết trên tài nguyên mạng ở compartment đích, thay vì chỉ cấp quyền Compute tại `shop/dev`. Không nên giải quyết lỗi thiếu quyền bằng cách chuyển subnet sang compartment ứng dụng hoặc cấp `manage all-resources in tenancy`.

Một thỏa thuận sử dụng tài nguyên chung nên ghi rõ:

| Nội dung | Ví dụ cho mạng dùng chung |
| --- | --- |
| Chủ sở hữu | Nhóm nền tảng quản lý subnet và quy tắc mạng |
| Bên sử dụng | Pipeline hoặc nhóm triển khai Shop dev |
| Thao tác được phép | Thao tác sử dụng subnet cần cho quy trình triển khai đã chọn |
| Thao tác giữ lại cho nền tảng | Thay đổi định tuyến, cấu hình bảo mật hoặc xóa mạng |
| Phạm vi ảnh hưởng | Workload đang dùng cùng subnet hoặc thành phần kết nối |
| Quy trình thay đổi | Đánh giá phụ thuộc và thông báo trước khi sửa cấu hình |

Tách `shared-prod` khỏi `shared-nonprod` giúp làm rõ mức kiểm soát thay đổi, nhưng mức độc lập thực sự còn phụ thuộc tài nguyên có được tách hay không. Nếu cả hai compartment vẫn phụ thuộc cùng thiết bị, đường kết nối hoặc dịch vụ trung tâm, rủi ro dùng chung vẫn tồn tại.

Cần kiểm tra riêng phụ thuộc về backup, log, khóa và dữ liệu. Không đặt toàn bộ bản sao lưu của mọi hệ thống vào một compartment chỉ vì dễ nhìn trên Console nếu việc đó tạo ra một nhóm người có khả năng xóa bản sao của tất cả sản phẩm.

## 7. Kết hợp compartment, tag và kiểm soát sử dụng

### 7.1. Dùng tag cho các chiều phân loại bổ sung

Trong cây dự án → môi trường, bộ phận tài chính vẫn có thể cần báo cáo theo đơn vị kinh doanh. Thay vì nhân đôi tài nguyên hoặc dựng lại cây, thiết kế thêm defined tag có quy ước rõ ràng:

| Thuộc tính minh họa | Giá trị ví dụ | Mục đích |
| --- | --- | --- |
| `Governance.OwnerTeam` | `shop-platform` | Tìm nhóm chịu trách nhiệm |
| `Governance.Environment` | `dev`, `staging`, `prod` | Phân loại môi trường |
| `Finance.CostCenter` | `commerce` | Phân bổ chi phí nội bộ |
| `Governance.DataClass` | `internal`, `restricted` | Hỗ trợ kiểm kê theo mức nhạy cảm |
| `Governance.ExpiryDate` | Ngày hết hạn đã thống nhất | Theo dõi sandbox cần thu hồi |

Đây là tên namespace và key do tổ chức tự quy định cho ví dụ, không phải tag mặc định bắt buộc của OCI. Nhóm sở hữu quy ước phải xác định ai được đặt hoặc sửa giá trị. Một tag ghi `prod` không tự tạo quy trình phê duyệt production.

Phân biệt **tag gắn trên compartment** với **tag default**. OCI có cơ chế kế thừa defined tag từ compartment trong các dịch vụ đo lường như Cost Analysis, Usage Reports và Budget; cần đánh giá quy tắc ưu tiên khi báo cáo chi phí. Không nên suy ra mọi thuộc tính tag vật lý trên từng tài nguyên đều được cập nhật giống báo cáo. Xem [Tags and Tag Namespace Concepts](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagsandtagnamespaces.htm).

Tag default được dùng để áp dụng defined tag khi tạo tài nguyên trong phạm vi liên quan, gồm compartment con. Tạo hoặc sửa tag default không tự cập nhật hồi tố toàn bộ tài nguyên đã tồn tại. Sau cấu hình, cần kiểm tra tài nguyên mẫu và phần tài nguyên cũ cần bổ sung tag. Xem [Managing Tag Defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagdefaults.htm).

### 7.2. Không nhầm budget với quota

| Cơ chế | Câu hỏi chính | Cách dùng trong thiết kế |
| --- | --- | --- |
| Budget | Chi phí đang hoặc có thể vượt mức dự kiến không? | Theo dõi và cảnh báo cho người phụ trách |
| Compartment quota | Compartment được sử dụng bao nhiêu tài nguyên trong loại và phạm vi được hỗ trợ? | Kiểm soát phân bổ tài nguyên cho dự án hoặc sandbox |
| Service limit | Tenancy được OCI cho phép sử dụng tới mức nào trong phạm vi tương ứng? | Đánh giá khả năng đáp ứng trước khi triển khai |

Budget là giới hạn mềm phục vụ theo dõi chi phí; tự tạo budget không đồng nghĩa instance sẽ bị dừng khi chi phí chạm ngưỡng. Vì vậy, sandbox vẫn cần người nhận cảnh báo và hành động xử lý cụ thể. Xem [Creating a Budget](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/create-budget.htm).

Compartment quota do quản trị viên đặt, còn service limit do OCI xác định cho tenancy theo từng phạm vi. Quota không làm tăng service limit và không bảo đảm luôn có năng lực vật lý sẵn sàng để cấp tài nguyên. Xem [Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm).

Trong bài toán Shop, có thể giao budget riêng cho dev và prod, đặt quota phù hợp cho dev, đồng thời phân bổ chi phí nền tảng dùng chung bằng quy ước nội bộ. Việc phân bổ shared cần nhất quán: chẳng hạn dùng tỷ lệ sử dụng hoặc tỷ lệ thỏa thuận, thay vì tùy ý chuyển tài nguyên giữa compartment để thay đổi người chịu chi phí.

## 8. Chuẩn hóa thông tin trước khi tạo compartment

Mỗi compartment nên có một hồ sơ thiết kế ngắn. Ví dụ sau mô tả `org/workloads/shop/prod`:

| Trường thông tin | Giá trị thiết kế minh họa |
| --- | --- |
| Mục đích | Chứa workload production của sản phẩm Shop |
| Chủ sở hữu nghiệp vụ | Đại diện sản phẩm Shop |
| Nhóm vận hành | `ShopProdOperators` |
| Người quản lý policy | Nhóm IAM hoặc nền tảng được giao |
| Tài nguyên dự kiến | Compute, lưu trữ, thành phần cơ sở dữ liệu thuộc phạm vi sản phẩm |
| Phụ thuộc | Mạng production dùng chung, khóa và dịch vụ giám sát đã thống nhất |
| Quy tắc dữ liệu | Theo phân loại dữ liệu thực tế của Shop |
| Chi phí | Cost center `commerce`, người nhận cảnh báo được chỉ định |
| Tính sẵn sàng | Yêu cầu phục hồi được thiết kế ở kiến trúc dịch vụ |
| Vòng đời | Kết thúc khi sản phẩm ngừng phục vụ và xử lý dữ liệu hoàn tất |

Tên nên dễ hiểu, có quy ước ổn định và tránh thông tin nhạy cảm. OCI yêu cầu tên compartment duy nhất trong cùng compartment cha; các dự án khác nhau có thể có compartment con cùng tên `dev`. Định danh OCID giúp phân biệt chúng trong tự động hóa. Xem [Creating a Compartment](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/To_create_a_compartment.htm).

Trong tài liệu vận hành, nên ghi đầy đủ đường dẫn thay vì chỉ ghi “compartment dev”. Trong mã triển khai, nên truyền OCID đúng phạm vi vào từng cấu hình, hạn chế cơ chế mặc định có thể khiến tài nguyên bị tạo nhầm ở root hoặc sai môi trường.

## 9. Thực hành tạo cây dự án và môi trường bằng OCI CLI

### 9.1. Phạm vi thực hành

Bài thực hành tạo một dự án mẫu dưới compartment lab đã được quản trị viên cấp quyền:

```text
compartment lab đã được giao
└── lab-shop
    ├── dev
    ├── staging
    └── prod
```

Tên `prod` trong bài thực hành chỉ minh họa mô hình tổ chức. Không dùng tài nguyên hoặc dữ liệu production thật để thử quyền.

Điều kiện chuẩn bị:

- OCI CLI đã được cài và xác thực bằng profile phù hợp.
- Có OCID của compartment lab và quyền tạo compartment con trong đó.
- Tên `lab-shop` chưa được dùng trong compartment cha; nếu đã có, cần xác định quyền sở hữu trước khi dùng lại hoặc đổi tên.
- Đã xác định nhóm thực hành và người có quyền thiết lập policy cho nhóm đó.

Các lệnh sau là ví dụ **PowerShell**. Không chứa khóa API hoặc thông tin đăng nhập trong nội dung lệnh.

### 9.2. Tạo compartment dự án và ba môi trường

Thay chuỗi placeholder trong `$LabParentId` bằng OCID thật. Tham số `--compartment-id` của lệnh tạo là **OCID của compartment cha**, còn giá trị `data.id` trả về là OCID của compartment vừa tạo.

```powershell
$LabParentId = '<OCID_COMPARTMENT_LAB>'

$ShopId = oci iam compartment create `
    --compartment-id $LabParentId `
    --name 'lab-shop' `
    --description 'Lab project: Shop; owner: training team' `
    --wait-for-state ACTIVE `
    --query 'data.id' `
    --raw-output

if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ShopId)) {
    throw 'Khong tao duoc compartment lab-shop; dung de kiem tra.'
}
$ShopId = $ShopId.Trim()

$EnvironmentIds = @{}
foreach ($EnvironmentName in @('dev', 'staging', 'prod')) {
    $EnvironmentId = oci iam compartment create `
        --compartment-id $ShopId `
        --name $EnvironmentName `
        --description "Shop lab environment: $EnvironmentName" `
        --wait-for-state ACTIVE `
        --query 'data.id' `
        --raw-output

    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($EnvironmentId)) {
        throw "Khong tao duoc $EnvironmentName; dung de kiem tra."
    }
    $EnvironmentIds[$EnvironmentName] = $EnvironmentId.Trim()
}

$EnvironmentIds
```

Lệnh dùng `--wait-for-state ACTIVE` để không sử dụng ngay đối tượng còn đang ở trạng thái tạo. Nếu timeout, kiểm tra lại đối tượng trước khi chạy lại; thao tác tạo không phải cơ chế tự đồng bộ một cây đã có sẵn. Nếu vòng lặp dừng giữa chừng, compartment đã tạo thành công vẫn còn tồn tại. Xem [OCI CLI: compartment create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/compartment/create.html).

Trong triển khai lặp lại, nên mô hình hóa cây bằng công cụ Infrastructure as Code hoặc quy trình có kiểm tra trạng thái hiện hữu, thay vì liên tục chạy lại lệnh tạo. Mỗi cây cần có chủ sở hữu cấu hình thống nhất để tránh hai pipeline cùng quản lý một compartment.

### 9.3. Xác minh cấu trúc và quyền

Liệt kê các compartment con trực tiếp của dự án:

```powershell
oci iam compartment list `
    --compartment-id $ShopId `
    --lifecycle-state ACTIVE `
    --all `
    --query 'data[].{Name:name,Id:id,Parent:"compartment-id",State:"lifecycle-state"}' `
    --output table
```

Kỳ vọng có `dev`, `staging`, `prod` với cùng `Parent` là `$ShopId`. Lệnh kiểm tra cấu trúc, không chứng minh người dùng đã có quyền thao tác trên mọi tài nguyên bên trong. `--all` lấy đủ các trang kết quả; khi truy vấn compartment không phải root, thao tác list trả về con trực tiếp, không tự duyệt toàn bộ cây. Xem [OCI CLI: compartment list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/compartment/list.html).

Để thử cấp quyền bằng OCID, người quản trị có thể dùng dạng statement sau sau khi thay placeholder và chọn đúng nhóm/domain:

```text
Allow group 'Default'/'ShopLabOperators' to manage instance-family in compartment id <DEV_COMPARTMENT_OCID>
```

Statement này chỉ minh họa phạm vi quyền với instance; không tự cấp mọi phụ thuộc cần để launch instance. Người quản trị cần bổ sung đúng quyền đã được phân tích cho bài thực hành, tương tự phần thiết kế IAM phía trên.

Dùng một tài khoản thử nghiệm không thuộc nhóm quản trị rộng để kiểm tra cả hai chiều:

| Phép kiểm tra | Kết quả cần đạt |
| --- | --- |
| Thực hiện thao tác được giao trên tài nguyên dev có sẵn | Thành công nếu đủ quyền và phụ thuộc |
| Thực hiện thao tác tương ứng trên tài nguyên prod đã biết OCID | Bị từ chối theo mô hình quyền của bài lab |
| Thử thay đổi policy ngoài phạm vi được giao | Bị từ chối |
| Kiểm tra thao tác sử dụng tài nguyên chung | Chỉ thành công với phụ thuộc đã được cho phép |

Không dùng việc “không nhìn thấy tài nguyên prod” làm bằng chứng duy nhất. Cần kiểm tra đúng thao tác API và định danh tài nguyên; thông báo không tìm thấy có thể liên quan tới quyền, region hoặc định danh sai. Nếu tài khoản thử nghiệm vẫn làm được thao tác production, hãy kiểm tra các nhóm khác và policy ở cấp trên trước khi sửa cây.

Sau thực hành, kiểm kê những gì đã tạo, thu hồi quyền lab tạm thời và xử lý compartment theo quy trình môi trường học. Không coi việc xóa compartment là thao tác tự động dọn sạch mọi tài nguyên và dữ liệu bên trong.

## 10. Thay đổi cấu trúc khi hệ thống đã hoạt động

Có hai thao tác khác nhau cần đánh giá riêng:

- **Di chuyển tài nguyên:** đổi compartment chứa tài nguyên cụ thể.
- **Di chuyển compartment:** đổi vị trí của một nhánh trong cây.

Khi di chuyển tài nguyên, quyền ở compartment đích có thể thay đổi người được truy cập. Khả năng di chuyển và hành vi tài nguyên phụ thuộc khác nhau theo dịch vụ; một số phụ thuộc đi cùng, một số phải xử lý riêng. Các giới hạn liên quan đến security zone cũng cần xét nếu môi trường dùng tính năng này. Xem [Moving a Resource Between Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/To_move_a_resource_to_a_different_compartment.htm).

Khi di chuyển compartment, phải đánh giá cả quyền kế thừa từ cha cũ và cha mới. OCI có thể tự cập nhật một số policy có đường dẫn compartment trong các điều kiện nhất định; không nên dựa vào giả định mọi policy đều được sửa hoặc không policy nào được sửa. Xem [Moving a Compartment](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/To_move_a_compartment.htm) và [Working with Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/Working_with_Compartments.htm).

Một kế hoạch thay đổi nên có các bước sau:

1. Lập danh sách tài nguyên, phụ thuộc và tài khoản hoặc pipeline đang truy cập.
2. So sánh quyền hiệu lực trước và sau thay đổi, gồm allow và deny nếu có.
3. Xác định tác động đến cách phân loại chi phí, quota, cấu hình giám sát và tự động hóa.
4. Thử trên môi trường phi production có cấu trúc tương đương.
5. Thực hiện trong khoảng thời gian đã thống nhất và xác minh hoạt động dịch vụ.
6. Cập nhật tài liệu, cấu hình triển khai và bằng chứng xác minh sau thay đổi.

Không dùng cách chuyển tài nguyên từ `dev` sang `prod` như quy trình phát hành mặc định. Phát hành thường cần triển khai cấu hình hoặc phiên bản đã được kiểm soát vào môi trường production; đổi compartment chỉ thay đổi phạm vi tổ chức tài nguyên, không thay thế kiểm thử, phê duyệt hoặc xử lý dữ liệu.

## 11. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Đặt mọi workload ở root | Nhiều công việc nhỏ đòi hỏi quyền quá rộng | Chuyển dần sang phạm vi dự án và môi trường có chủ sở hữu |
| Gộp dev và prod rồi chỉ phân biệt tên tài nguyên | Dễ cấp nhầm quyền hoặc thao tác nhầm môi trường | Tách compartment khi yêu cầu quyền và vòng đời khác nhau |
| Cấp `manage all-resources` ở cha cho thuận tiện | Quyền lan xuống các nhánh cần bảo vệ | Cấp theo công việc ở phạm vi đã phân tích |
| Tạo một compartment cho từng instance | Policy, kiểm kê và tự động hóa khó duy trì | Gom theo ranh giới trách nhiệm có ý nghĩa |
| Đưa mọi chiều phân loại vào cây | Cây sâu và dễ thay đổi theo báo cáo | Dùng tag cho thuộc tính bổ sung |
| Có `shared` nhưng không có thỏa thuận sử dụng | Phát sinh quyền rộng hoặc thay đổi ảnh hưởng nhiều đội | Ghi rõ người sở hữu, thao tác và phụ thuộc |
| Tạo sandbox không có người nhận cảnh báo và ngày kết thúc | Tài nguyên thử nghiệm tiếp tục phát sinh chi phí | Gắn chủ sở hữu, budget, quota phù hợp và quy trình thu hồi |
| Nhầm compartment với mạng hoặc kiến trúc dự phòng | Đánh giá sai mức cô lập và khả năng phục hồi | Kiểm tra riêng quyền, kết nối, dữ liệu và tính sẵn sàng |

## 12. Tiêu chí hoàn tất một thiết kế compartment

Một cây compartment có thể đưa vào triển khai khi đội ngũ giải thích và kiểm chứng được các điểm sau:

- Mỗi nhánh có mục đích và chủ sở hữu cụ thể; tên gọi không phải lý do duy nhất để tồn tại.
- Thứ tự tổ chức, dự án và môi trường phù hợp cách ủy quyền dài hạn.
- Môi trường có mức rủi ro khác nhau được cấp quyền phù hợp, kể cả khi xét quyền ở cha và các nhóm khác.
- Tài nguyên dùng chung có trách nhiệm vận hành và quyền sử dụng chéo được mô tả rõ.
- Các chiều phân loại chi phí và dữ liệu có quy ước tag được quản lý.
- Budget, quota và service limit được hiểu đúng vai trò.
- Việc tạo cây và truyền OCID vào cấu hình triển khai có thể lặp lại và kiểm tra được.
- Có quy trình tiếp nhận dự án mới, thay đổi cấu trúc và kết thúc dự án.
- Yêu cầu mạng, giám sát, backup và phục hồi được gắn với thiết kế dịch vụ tương ứng.

Với ví dụ Shop, kết quả mong muốn là đội phát triển thao tác được trong dev, đội vận hành quản lý được production, nhóm nền tảng kiểm soát được phần dùng chung và người phụ trách chi phí giải trình được mức sử dụng. Cây compartment cần làm rõ những trách nhiệm đó trước khi tổ chức mở rộng thêm dịch vụ OCI.
