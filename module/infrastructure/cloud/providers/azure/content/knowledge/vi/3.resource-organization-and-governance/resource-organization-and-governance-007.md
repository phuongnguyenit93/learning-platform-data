# Ngăn thao tác nhầm bằng resource lock

Trong Azure, một thao tác xóa nhầm có thể làm gián đoạn ứng dụng, mất cấu hình hoặc khiến dữ liệu khó khôi phục. Azure Resource Manager cung cấp **resource lock** (khóa tài nguyên) để hạn chế một số thao tác quản lý quan trọng ở cấp subscription, resource group hoặc tài nguyên riêng lẻ. Khi được đặt đúng phạm vi, khóa giúp ngăn người dùng vô tình xóa hoặc thay đổi tài nguyên quan trọng, kể cả khi họ có quyền RBAC cho thao tác đó.

Bài học này thuộc chương **Tổ chức và quản trị tài nguyên** của module **CLOUD_PROVIDERS_AZURE**. Module khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; đồng thời hướng dẫn triển khai, giám sát, bảo vệ và kiểm soát chi phí cho một kiến trúc ứng dụng. Resource lock là một lớp bảo vệ trong quản trị vòng đời tài nguyên, cần được phối hợp với RBAC, Azure Policy, sao lưu và quy trình thay đổi.

Sau bài học, bạn có thể:

- Giải thích resource lock bảo vệ tài nguyên ở lớp quản lý Azure như thế nào.
- Phân biệt hai loại khóa **CanNotDelete** và **ReadOnly**.
- Chọn phạm vi khóa phù hợp và dự đoán tác động kế thừa xuống tài nguyên con.
- Tạo, liệt kê, kiểm tra và gỡ khóa bằng Azure Portal hoặc Azure CLI.
- Xử lý tình huống triển khai, cập nhật, di chuyển hoặc xóa tài nguyên bị khóa.
- Kết hợp khóa với RBAC và các biện pháp bảo vệ dữ liệu khác.

## 1. Resource lock giải quyết vấn đề gì?

Resource lock là một đối tượng quản lý của Azure Resource Manager (ARM), dùng để hạn chế các thao tác quản lý đối với phạm vi đã khóa. Bạn có thể đặt khóa ở ba phạm vi chính:

1. **Subscription:** bảo vệ nhiều resource group và tài nguyên trong subscription.
2. **Resource group:** bảo vệ resource group cùng các tài nguyên nằm trong nhóm.
3. **Resource:** bảo vệ một tài nguyên cụ thể, chẳng hạn storage account hoặc virtual network.

Ví dụ, một nhóm phát triển có thể có quyền Contributor để triển khai và cập nhật tài nguyên. Nếu một người vô tình chọn xóa storage account chứa dữ liệu dùng chung, RBAC có thể cho phép thao tác đó. Một khóa **CanNotDelete** đặt trên storage account sẽ chặn thao tác xóa ở lớp quản lý cho đến khi khóa được gỡ.

Resource lock đặc biệt hữu ích với:

- Resource group chứa tài nguyên dùng chung của nhiều nhóm.
- Storage account, database, virtual network hoặc dịch vụ nền tảng quan trọng.
- Môi trường production hoặc môi trường có cấu hình khó tái tạo.
- Tài nguyên cần giữ nguyên trong thời gian kiểm toán, vận hành hoặc chuyển đổi hệ thống.

Khóa là một biện pháp phòng ngừa thao tác quản trị nhầm. Nó không tự sao lưu dữ liệu, không thay thế phân quyền và không bảo đảm mọi thao tác trên dữ liệu đều bị chặn.

## 2. Hai loại resource lock

Azure Resource Manager cung cấp hai cấp khóa:

| Lock level | Đọc tài nguyên | Thay đổi cấu hình | Xóa tài nguyên |
|---|---|---|---|
| **CanNotDelete** | Được phép nếu RBAC cho phép | Được phép nếu RBAC cho phép | Bị chặn |
| **ReadOnly** | Được phép nếu RBAC cho phép | Bị chặn ở lớp quản lý | Bị chặn |

### CanNotDelete

**CanNotDelete** cho phép người dùng tiếp tục đọc và cập nhật tài nguyên, nhưng ngăn việc xóa tài nguyên qua Azure Resource Manager. Đây thường là lựa chọn phù hợp khi nhóm vận hành vẫn cần thay đổi cấu hình nhưng muốn tránh xóa nhầm.

Ví dụ, một virtual network đang được nhiều ứng dụng sử dụng có thể cần thay đổi cấu hình subnet theo kế hoạch. Khóa **CanNotDelete** vẫn cho phép thao tác cập nhật được RBAC cấp quyền, nhưng chặn yêu cầu xóa virtual network.

### ReadOnly

**ReadOnly** cho phép đọc tài nguyên nhưng chặn các thao tác cập nhật và xóa qua Azure Resource Manager. Khóa này mạnh hơn **CanNotDelete** và cần được áp dụng thận trọng.

Ví dụ, sau khi hoàn tất cấu hình một resource group chứa môi trường tham chiếu chỉ đọc, người quản trị có thể đặt **ReadOnly** để ngăn thay đổi cấu hình ngoài quy trình được phê duyệt.

**ReadOnly** có thể làm gián đoạn những thao tác vận hành mà bạn không ngờ tới. Một số API quản lý dùng phương thức POST ngay cả khi mục đích là truy xuất thông tin, chẳng hạn thao tác liệt kê access key của storage account. Khóa ReadOnly có thể chặn những lời gọi như vậy. Hãy kiểm thử các thao tác quản trị, tự động hóa và tích hợp ứng dụng trước khi áp dụng rộng.

### Chọn loại khóa theo mục tiêu

- Muốn giữ tài nguyên tồn tại nhưng vẫn cho phép cập nhật: chọn **CanNotDelete**.
- Muốn ngăn cả cập nhật lẫn xóa qua ARM trong một giai đoạn ổn định: cân nhắc **ReadOnly**.
- Chỉ muốn hạn chế một người hoặc một nhóm người: xem lại RBAC và quy trình phê duyệt; khóa không phải công cụ phân quyền theo danh tính.

Khóa không cấp thêm quyền cho người dùng. Nếu RBAC không cho phép đọc hoặc cập nhật, việc có khóa cũng không làm thao tác đó trở nên hợp lệ.

## 3. Phạm vi và cơ chế kế thừa

Khóa có hiệu lực tại phạm vi được tạo và được kế thừa bởi các tài nguyên con trong phạm vi đó. Ví dụ:

~~~text
Subscription: sub-production
    |
    +-- Resource group: rg-app-prod
    |       [CanNotDelete]
    |       |
    |       +-- Virtual network: vnet-app
    |       +-- Virtual machine: vm-app-01
    |       +-- Storage account: stappdata
    |
    +-- Resource group: rg-monitoring
            +-- Log Analytics workspace
~~~

Trong sơ đồ, khóa **CanNotDelete** ở **rg-app-prod** bảo vệ resource group và các tài nguyên nằm trong nhóm khỏi bị xóa qua ARM. Những tài nguyên ở **rg-monitoring** không chịu khóa của **rg-app-prod**.

### Đặt khóa ở phạm vi nào?

| Phạm vi | Phạm vi ảnh hưởng | Khi phù hợp |
|---|---|---|
| Subscription | Resource group và tài nguyên thuộc subscription | Subscription chuyên dùng cho môi trường quan trọng và cần chính sách bảo vệ rộng |
| Resource group | Chính resource group và các tài nguyên con | Một ứng dụng hoặc một môi trường có vòng đời chung |
| Resource | Chỉ tài nguyên được chọn | Cần bảo vệ một database, storage account hoặc thành phần nền tảng riêng lẻ |

Khóa ở phạm vi cha tiếp tục có hiệu lực đối với tài nguyên con. Nếu một resource group đang kế thừa **ReadOnly** từ subscription, việc tạo thêm **CanNotDelete** ở resource group không làm phạm vi đó trở lại trạng thái có thể cập nhật. Bạn phải xử lý khóa ở phạm vi cha theo đúng quy trình và quyền được cấp.

Nhiều khóa có thể cùng tác động đến một tài nguyên. Hãy đánh giá toàn bộ khóa được kế thừa và khóa trực tiếp trước khi kết luận thao tác nào được phép. Một khóa hạn chế hơn ở bất kỳ phạm vi cha nào vẫn có thể chặn thao tác, dù khóa trực tiếp của tài nguyên có mức hạn chế thấp hơn.

### Cân nhắc khi chọn phạm vi

Đặt khóa ở subscription có thể bảo vệ nhiều tài nguyên nhưng cũng dễ cản trở hoạt động triển khai thông thường. Đặt khóa ở resource group giúp gắn chính sách bảo vệ với vòng đời của một ứng dụng. Đặt khóa ở tài nguyên cụ thể giúp giới hạn ảnh hưởng khi chỉ một thành phần cần được bảo vệ.

Trước khi đặt khóa ở phạm vi rộng, hãy xác định:

- Những nhóm và tài nguyên nào sẽ kế thừa khóa.
- Nhóm triển khai có cần tạo, cập nhật hoặc xóa tài nguyên trong phạm vi đó không.
- Công cụ CI/CD, autoscaling và dịch vụ quản lý có cần thực hiện thao tác bị khóa không.
- Ai có quyền quản lý khóa và quy trình gỡ khóa khi cần thay đổi khẩn cấp.

## 4. Resource lock và RBAC phối hợp như thế nào?

Azure RBAC xác định **ai được phép thực hiện hành động nào** trên một phạm vi. Resource lock xác định **những thao tác quản lý nào bị hạn chế** tại phạm vi đó. Hai cơ chế hoạt động cùng nhau.

| Tình huống | RBAC | Resource lock | Kết quả |
|---|---|---|---|
| Người dùng không có quyền xóa, tài nguyên không khóa | Không cho phép xóa | Không có khóa | Không xóa được |
| Người dùng có quyền xóa, tài nguyên có **CanNotDelete** | Cho phép xóa | Chặn xóa | Không xóa được |
| Người dùng có quyền cập nhật, tài nguyên có **ReadOnly** | Cho phép cập nhật | Chặn cập nhật qua ARM | Không cập nhật được |
| Người dùng có quyền đọc, tài nguyên có **CanNotDelete** | Cho phép đọc | Không chặn đọc | Đọc được |

Để tạo hoặc xóa management lock, người thực hiện cần quyền quản lý khóa tại phạm vi tương ứng, thường thông qua vai trò Owner hoặc User Access Administrator, hoặc vai trò tùy chỉnh có các hành động quản lý lock cần thiết trong **Microsoft.Authorization/locks**. Vai trò Contributor thông thường không mặc nhiên có quyền quản lý các khóa này.

Điều đó giải thích vì sao một người có thể quản lý tài nguyên nhưng không thể tự gỡ khóa đang cản trở thao tác. Trong môi trường doanh nghiệp, việc giữ quyền quản lý lock cho nhóm quản trị giúp tránh trường hợp người triển khai tự gỡ lớp bảo vệ để hoàn tất một thao tác xóa.

## 5. Tạo và quản lý khóa bằng Azure Portal

Bạn có thể tạo khóa tại subscription, resource group hoặc trang quản lý của một tài nguyên.

### Tạo khóa cho resource group

1. Mở [Azure Portal](https://portal.azure.com/) và đăng nhập bằng tài khoản có quyền phù hợp.
2. Tìm **Resource groups** và mở resource group cần bảo vệ.
3. Trong phần **Settings**, mở **Locks**. Tên hoặc vị trí mục có thể thay đổi theo phiên bản giao diện.
4. Chọn **Add**.
5. Nhập tên dễ hiểu, ví dụ **lock-protect-rg-app-prod**.
6. Chọn **Delete** tương ứng với **CanNotDelete**, hoặc **Read-only** tương ứng với **ReadOnly**.
7. Thêm ghi chú giải thích lý do khóa và nhóm chịu trách nhiệm nếu giao diện hỗ trợ.
8. Lưu khóa, sau đó mở danh sách Locks để xác nhận khóa đã xuất hiện đúng phạm vi.

### Kiểm tra khóa ở tài nguyên

Mở tài nguyên cần kiểm tra và xem mục **Locks**. Nếu thao tác bị chặn, kiểm tra cả khóa trực tiếp trên tài nguyên và khóa được kế thừa từ resource group hoặc subscription. Chỉ xem danh sách ở trang tài nguyên đôi khi chưa đủ để hiểu toàn bộ phạm vi bảo vệ.

### Gỡ khóa trong Portal

1. Mở đúng phạm vi đang chứa khóa.
2. Vào **Settings > Locks**.
3. Chọn khóa cần gỡ và xác nhận tên, loại khóa, phạm vi cùng lý do thay đổi.
4. Xóa khóa bằng tài khoản có quyền quản lý lock.
5. Thực hiện thay đổi đã được phê duyệt.
6. Tạo lại khóa nếu tài nguyên vẫn cần được bảo vệ.

Không gỡ một khóa kế thừa bằng cách xóa khóa ở tài nguyên con. Bạn phải tìm đúng phạm vi nơi khóa được tạo và xử lý tại đó.

## 6. Tạo và quản lý khóa bằng Azure CLI

Azure CLI cung cấp nhóm lệnh **az lock** để quản lý resource lock. Trước khi chạy lệnh, đăng nhập và xác nhận subscription:

~~~bash
az login
az account show --output table
~~~

Nếu tài khoản có nhiều subscription, chọn đúng subscription:

~~~bash
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --output table
~~~

### Tạo CanNotDelete ở resource group

Giả sử resource group cần bảo vệ là **rg-app-prod**:

~~~bash
az lock create --name lock-protect-rg-app-prod --lock-type CanNotDelete --resource-group rg-app-prod --notes "Ngăn xóa nhầm tài nguyên ứng dụng production"
~~~

Tham số **--lock-type** nhận giá trị **CanNotDelete** hoặc **ReadOnly**. Tên khóa nên thể hiện mục đích và phạm vi để người vận hành dễ nhận biết.

### Liệt kê và xem thông tin khóa

~~~bash
az lock list --resource-group rg-app-prod --output table
~~~

Để xem chi tiết một khóa:

~~~bash
az lock show --name lock-protect-rg-app-prod --resource-group rg-app-prod --output json
~~~

Kiểm tra các thuộc tính như tên khóa, cấp khóa, ghi chú và phạm vi. Nếu một thao tác vẫn bị chặn sau khi bạn tạo hoặc gỡ khóa, hãy kiểm tra thêm khóa ở subscription và các phạm vi cha.

### Tạo khóa cho một tài nguyên cụ thể

Ví dụ, khóa riêng một storage account:

~~~bash
az lock create --name lock-protect-storage --lock-type CanNotDelete --resource-group rg-app-prod --resource-name stappdata --resource-type Microsoft.Storage/storageAccounts --notes "Bảo vệ storage account dùng chung"
~~~

Khi khóa một tài nguyên cụ thể, cần truyền đúng resource group, resource name và resource type. Với tài nguyên có tên đầy đủ hoặc loại tài nguyên lồng nhau, hãy xác nhận resource ID và cú pháp của nhà cung cấp trước khi tạo khóa.

### Gỡ khóa

Nếu khóa được tạo ở cấp resource group, có thể gỡ bằng:

~~~bash
az lock delete --name lock-protect-rg-app-prod --resource-group rg-app-prod
~~~

Nếu khóa được tạo ở cấp tài nguyên, dùng đúng thông tin nhận diện tài nguyên:

~~~bash
az lock delete --name lock-protect-storage --resource-group rg-app-prod --resource-name stappdata --resource-type Microsoft.Storage/storageAccounts
~~~

Sau khi gỡ, liệt kê khóa một lần nữa để xác nhận. Nếu khóa cùng tên ở nhiều phạm vi, không dựa vào tên đơn lẻ; hãy xác định đúng scope hoặc resource ID.

### Khóa ở cấp subscription

Để bảo vệ toàn bộ subscription khỏi thao tác xóa, có thể tạo khóa ở scope subscription:

~~~bash
az lock create --name lock-protect-subscription --lock-type CanNotDelete --scope "/subscriptions/<SUBSCRIPTION_ID>" --notes "Ngăn xóa nhầm tài nguyên trong subscription"
~~~

Khóa ở subscription có thể ảnh hưởng đến nhiều nhóm và quy trình triển khai. Chỉ sử dụng khi phạm vi subscription đã được thống nhất với nhóm vận hành và có quy trình quản lý khóa rõ ràng.

## 7. Những tác động cần kiểm tra trước khi áp dụng

Resource lock bảo vệ thao tác ở **management plane** (lớp quản lý tài nguyên thông qua Azure Resource Manager). Khóa không phải là cơ chế kiểm soát toàn bộ thao tác dữ liệu bên trong dịch vụ.

Ví dụ, **CanNotDelete** trên storage account ngăn xóa chính storage account qua ARM, nhưng không tự ngăn một ứng dụng hoặc người dùng có quyền data plane xóa blob bên trong. Tương tự, khóa resource group không thay thế các cơ chế bảo vệ dữ liệu của database hoặc kho lưu trữ.

Trước khi đưa khóa vào môi trường vận hành, hãy đánh giá:

- **Triển khai:** template, pipeline hoặc công cụ IaC có cần tạo, thay đổi hoặc xóa tài nguyên trong phạm vi không?
- **Mở rộng tự động:** dịch vụ có cần tạo hoặc xóa instance, NIC, disk hay thành phần phụ trợ không?
- **Tích hợp:** thao tác quản lý nào của ứng dụng cần gọi API bị ảnh hưởng bởi **ReadOnly**?
- **Di chuyển:** việc move tài nguyên giữa resource group hoặc subscription có thể bị chặn bởi khóa ở nguồn hoặc đích.
- **Xóa theo vòng đời:** quy trình dọn môi trường thử nghiệm có thể không hoàn tất nếu resource group hoặc tài nguyên còn khóa.
- **Vận hành dữ liệu:** thao tác đọc/ghi dữ liệu cần RBAC và cơ chế bảo vệ riêng, không thể suy ra từ resource lock.

Một **ReadOnly** lock ở subscription có thể chặn việc tạo resource group hoặc tài nguyên mới trong phạm vi. Một **CanNotDelete** lock ở resource group vẫn cho phép cập nhật, nhưng chặn xóa nhóm hoặc tài nguyên con. Vì vậy, không nên áp dụng **ReadOnly** ở phạm vi rộng chỉ để phòng ngừa xóa nhầm.

## 8. Resource lock không thay thế các biện pháp bảo vệ khác

Để bảo vệ một ứng dụng Azure, hãy kết hợp nhiều lớp kiểm soát:

| Cơ chế | Mục đích chính | Ví dụ sử dụng |
|---|---|---|
| Azure RBAC | Giới hạn danh tính và hành động được phép | Chỉ nhóm quản trị có quyền xóa resource group |
| Resource lock | Chặn xóa hoặc cập nhật ở management plane | **CanNotDelete** cho database quan trọng |
| Azure Policy | Áp dụng và đánh giá quy tắc triển khai | Chỉ cho phép region hoặc SKU được phê duyệt |
| Backup và phục hồi | Khôi phục dữ liệu sau lỗi hoặc xóa | Backup database, khôi phục máy ảo |
| Soft delete hoặc immutable storage | Bảo vệ dữ liệu khỏi xóa hoặc sửa theo chính sách dịch vụ | Giữ lại blob đã xóa hoặc khóa chính sách lưu trữ bất biến |
| Quy trình thay đổi | Kiểm soát yêu cầu, phê duyệt và thời điểm thay đổi | Phiếu yêu cầu gỡ lock trước khi bảo trì |

Resource lock không tạo bản sao dữ liệu và không bảo đảm có thể khôi phục ứng dụng. Với dữ liệu quan trọng, hãy cấu hình backup, retention, soft delete hoặc immutable storage phù hợp với dịch vụ và yêu cầu khôi phục.

## 9. Quy trình vận hành khóa an toàn

Một quy trình quản lý khóa nên xác định rõ mục đích, chủ sở hữu và cách gỡ khóa:

1. **Phân loại tài nguyên:** xác định tài nguyên nào quan trọng và hậu quả nếu bị xóa hoặc sửa nhầm.
2. **Chọn phạm vi nhỏ nhất đáp ứng mục tiêu:** ưu tiên khóa resource hoặc resource group khi không cần bảo vệ toàn subscription.
3. **Chọn lock level:** dùng **CanNotDelete** cho nhu cầu ngăn xóa; chỉ dùng **ReadOnly** khi thật sự cần ngăn cập nhật.
4. **Kiểm tra tác động:** rà soát pipeline, autoscaling, API quản lý, quy trình backup, di chuyển và dọn dẹp.
5. **Đặt tên và ghi chú:** ghi mục đích, chủ sở hữu, ticket hoặc quy trình liên quan nếu có.
6. **Xác minh sau khi tạo:** kiểm tra scope, loại khóa, kế thừa và danh sách khóa.
7. **Rà soát định kỳ:** xác nhận khóa còn phù hợp, người chịu trách nhiệm còn đúng và không có khóa thừa.
8. **Gỡ khóa có kiểm soát:** ghi nhận lý do, người phê duyệt và thời gian; chỉ gỡ khóa cần thiết.
9. **Khôi phục bảo vệ:** sau khi thay đổi hoàn tất, tạo lại khóa và xác minh hiệu lực.

Resource lock không tự hết hạn. Nếu khóa chỉ cần tồn tại trong một khoảng thời gian, hãy ghi rõ thời hạn dự kiến và đưa việc rà soát/gỡ khóa vào quy trình vận hành. Không để khóa tạm thời trở thành cấu hình vĩnh viễn mà không có người sở hữu.

## 10. Xử lý sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không xóa được tài nguyên dù có quyền Owner | Tài nguyên đang chịu **CanNotDelete** hoặc **ReadOnly** lock | Kiểm tra Locks ở tài nguyên, resource group và subscription; gỡ khóa đúng scope nếu được phê duyệt |
| Không cập nhật được cấu hình | Có **ReadOnly** lock trực tiếp hoặc kế thừa | Xác định khóa gây ảnh hưởng; đánh giá thao tác cần thiết trước khi gỡ |
| Không tạo được tài nguyên mới trong resource group | Resource group hoặc subscription có **ReadOnly** lock | Kiểm tra scope cha và làm việc với nhóm quản lý lock |
| Đã xóa khóa ở tài nguyên nhưng thao tác vẫn bị chặn | Khóa đang được kế thừa từ resource group hoặc subscription | Liệt kê khóa ở từng scope cha và kiểm tra lại |
| Contributor không thể gỡ khóa | Vai trò Contributor không có quyền quản lý lock cần thiết | Yêu cầu Owner, User Access Administrator hoặc người có vai trò tùy chỉnh phù hợp xử lý |
| Ứng dụng không đọc được access key sau khi đặt ReadOnly | API quản lý dùng POST bị khóa | Kiểm tra loại API và cân nhắc thay đổi lock level hoặc thiết kế xác thực phù hợp |
| Pipeline triển khai thất bại khi xóa hoặc thay tài nguyên | Khóa cản trở thao tác IaC hoặc thay đổi vòng đời | Xác định chính xác thao tác bị chặn; thiết kế bước gỡ và tạo lại khóa có phê duyệt |
| Không di chuyển được tài nguyên | Khóa ở phạm vi nguồn hoặc đích chặn thao tác move | Kiểm tra cả hai scope, lên kế hoạch gỡ khóa tạm thời và xác minh sau di chuyển |

Khi xử lý lỗi, ghi lại resource ID, thao tác bị từ chối, mã lỗi và phạm vi đang kiểm tra. Không gỡ hàng loạt khóa chỉ để thử xem thao tác có chạy được hay không.

## 11. Bài thực hành: bảo vệ resource group ứng dụng

Trong bài tập này, bạn sẽ tạo **CanNotDelete** cho một resource group thử nghiệm, kiểm tra khóa và gỡ khóa. Hãy dùng subscription học tập hoặc môi trường sandbox được phép. Không chạy các lệnh trên resource group dùng chung hoặc production nếu chưa có phê duyệt.

### Chuẩn bị

- Đăng nhập Azure CLI và chọn đúng subscription.
- Có một resource group thử nghiệm tên **rg-lock-lab**.
- Có quyền tạo và xóa resource lock ở phạm vi resource group.

Nếu chưa có resource group thử nghiệm, tạo một nhóm riêng:

~~~bash
az group create --name rg-lock-lab --location southeastasia --tags environment=learning purpose=resource-lock-lab
~~~

Thay region bằng khu vực được phép trong subscription của bạn.

### Tạo và xác minh khóa

Tạo khóa ngăn xóa:

~~~bash
az lock create --name lock-protect-rg-lock-lab --lock-type CanNotDelete --resource-group rg-lock-lab --notes "Bài thực hành resource lock"
~~~

Liệt kê khóa:

~~~bash
az lock list --resource-group rg-lock-lab --output table
~~~

Xem chi tiết:

~~~bash
az lock show --name lock-protect-rg-lock-lab --resource-group rg-lock-lab --output json
~~~

Đối chiếu loại khóa, tên và phạm vi với thông tin vừa tạo.

### Quan sát tác động và dọn dẹp

1. Mở resource group trong Azure Portal và xác nhận khóa xuất hiện trong **Settings > Locks**.
2. Thử xóa resource group từ Portal trong môi trường lab. Yêu cầu xóa phải bị chặn do khóa **CanNotDelete**.
3. Không cần tạo tài nguyên tốn phí để kiểm tra hành vi này; resource group thử nghiệm đã đủ để quan sát việc khóa thao tác xóa nhóm.
4. Gỡ khóa bằng lệnh:

~~~bash
az lock delete --name lock-protect-rg-lock-lab --resource-group rg-lock-lab
~~~

5. Chạy lại lệnh liệt kê để xác nhận khóa đã được gỡ:

~~~bash
az lock list --resource-group rg-lock-lab --output table
~~~

6. Nếu nhóm chỉ dùng cho bài tập và không còn cần thiết, xóa resource group:

~~~bash
az group delete --name rg-lock-lab --yes
~~~

### Kết quả cần ghi lại

| Nội dung | Giá trị cần ghi |
|---|---|
| Subscription | Tên và ID subscription dùng cho lab |
| Resource group | **rg-lock-lab** |
| Lock name | **lock-protect-rg-lock-lab** |
| Lock level | **CanNotDelete** |
| Scope | Resource group |
| Kiểm tra | Kết quả liệt kê khóa và quan sát thao tác xóa bị chặn |
| Cleanup | Kết quả sau khi gỡ khóa và xóa resource group |

### Câu hỏi tự kiểm tra

1. **CanNotDelete** và **ReadOnly** khác nhau như thế nào?
2. Nếu đặt **CanNotDelete** ở resource group, các tài nguyên con chịu ảnh hưởng ra sao?
3. Vì sao người dùng có quyền Owner vẫn có thể không xóa được tài nguyên đang bị khóa?
4. Vì sao resource lock không thay thế backup hoặc immutable storage?
5. Một khóa **ReadOnly** ở subscription có thể ảnh hưởng đến pipeline triển khai như thế nào?
6. Nếu gỡ khóa trực tiếp trên tài nguyên mà thao tác vẫn bị chặn, bạn cần kiểm tra những phạm vi nào?

## 12. Tài liệu tham khảo

- [Lock your resources to protect your infrastructure](https://learn.microsoft.com/azure/azure-resource-manager/management/lock-resources) — khái niệm, phạm vi và cách hoạt động của resource lock.
- [Azure CLI: az lock](https://learn.microsoft.com/cli/azure/lock) — lệnh tạo, liệt kê, xem và xóa khóa.
- [Azure role-based access control (Azure RBAC)](https://learn.microsoft.com/azure/role-based-access-control/overview) — mô hình phân quyền trong Azure.
- [Azure Policy documentation](https://learn.microsoft.com/azure/governance/policy/overview) — quản trị và áp dụng chính sách tài nguyên.

Tên mục trong Portal, cú pháp lệnh và hành vi của từng dịch vụ có thể thay đổi theo phiên bản. Khi triển khai cho môi trường thật, hãy đối chiếu tài liệu hiện hành, kiểm tra quyền và thử nghiệm tác động của khóa trong môi trường không quan trọng trước.
