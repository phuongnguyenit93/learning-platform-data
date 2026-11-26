# Quyền khám phá mount mà repository cần sử dụng

## 1. Vì sao Vault Repository cần nhận diện mount?

Trong Spring Vault, ứng dụng Java thường truy cập HashiCorp Vault qua `VaultTemplate`, các thao tác KV (`VaultKeyValueOperations`) hoặc lớp repository lưu đối tượng theo khóa. Trước khi đọc, ghi hay liệt kê dữ liệu, client phải biết **secret engine được mount ở đâu** và **API của engine đó có dạng nào**. Đây là vấn đề đặc biệt quan trọng với KV v1 và KV v2: cùng một đường dẫn logic nhưng HTTP path, metadata và quy tắc phân quyền khác nhau.

Ví dụ, một ứng dụng quản lý đơn hàng lưu dữ liệu tại:

- **Mount:** `kv/`, nơi Vault gắn KV secrets engine.
- **Đường dẫn dữ liệu thuộc ứng dụng:** `apps/orders/`.
- **Khóa của đối tượng:** `order-001`.
- **Đường dẫn logic trong ứng dụng:** `apps/orders/order-001`.

Với KV v2, thao tác đọc giá trị tương ứng với API `GET /v1/kv/data/apps/orders/order-001`, trong khi liệt kê tên khóa dùng `LIST /v1/kv/metadata/apps/orders`. Đường dẫn `kv` là mount, còn `apps/orders/...` là đường dẫn bên trong engine. Nhầm lẫn hai phần dẫn đến lỗi cấu hình và cấp quyền sai.

**Khám phá mount (mount discovery)** là quá trình client hoặc thành phần tích hợp xác định secret engine ứng với đường dẫn yêu cầu, đôi khi đọc thông tin về loại và phiên bản KV. Không phải mọi lệnh repository đều bắt buộc gọi API khám phá: nếu backend và phiên bản đã được cấu hình tường minh, một số luồng làm việc trực tiếp với API dữ liệu. Hãy xác định hành vi theo phiên bản Spring Vault, cách khởi tạo repository và cấu hình thực tế đang dùng.

## 2. Ba lớp quyền cần phân biệt

| Lớp | Đường dẫn / đối tượng | Mục đích | Nguyên tắc phân quyền |
|---|---|---|---|
| Nhận diện mount | Thông tin về engine tại `kv/`, có thể qua `sys/internal/ui/mounts/<path>` | Xác định engine và lựa chọn API phù hợp | Phụ thuộc cách client khám phá và cơ chế kiểm tra quyền của Vault; không mặc định cấp quyền quản trị hệ thống |
| Truy cập giá trị | KV v2: `kv/data/apps/orders/*` | Đọc, tạo, cập nhật và xóa giá trị | Cấp đúng capabilities cho thao tác repository cần thực hiện |
| Truy cập metadata / liệt kê | KV v2: `kv/metadata/apps/orders` và các cấp con cần thiết | Liệt kê khóa, xem metadata phiên bản nếu cần | Cấp `list` hoặc `read` có chủ đích; tránh mở rộng phạm vi liệt kê |

Cần hiểu rõ hai endpoint dễ bị nhầm:

**`sys/internal/ui/mounts/<path>`:** một số phiên bản Vault và client sử dụng đường dẫn nội bộ này để nhận diện mount cho một đường dẫn secrets cụ thể. Vault có cơ chế kiểm tra quyền dựa trên quyền truy cập đường dẫn secrets tương ứng; việc viết ACL trực tiếp cho endpoint nội bộ **không phải giải pháp mặc định** cho lỗi preflight. API nội bộ cũng không nên được xem là hợp đồng ổn định để ứng dụng nghiệp vụ gọi thường xuyên. Khi có lỗi 403, trước tiên kiểm tra quyền ở đường dẫn dữ liệu thật, cách client tạo URL và phiên bản Vault.

**`sys/mounts` và các endpoint quản trị mount:** dành cho những hành động như liệt kê, bật/tắt hoặc cấu hình secret engines. Những quyền này thường thuộc trách nhiệm của đội vận hành Vault. Repository dùng để lưu đối tượng không cần khả năng bật engine, đọc danh sách mọi mount hoặc sửa cấu hình mount chỉ để thực hiện CRUD.

Một token có thể đọc `kv/data/apps/orders/order-001` thành công nhưng không thể gọi `vault secrets list`. Đó thường là trạng thái **đúng theo nguyên tắc ít quyền nhất**, không phải lỗi cần khắc phục bằng quyền quản trị.

## 3. KV v1 và KV v2 thay đổi đường dẫn ACL như thế nào?

Giả sử mount là `kv/` và object key là `apps/orders/order-001`.

| Thao tác | KV v1 | KV v2 | Capability thường cần |
|---|---|---|---|
| Đọc secret | `GET /v1/kv/apps/orders/order-001` | `GET /v1/kv/data/apps/orders/order-001` | `read` |
| Ghi secret mới / cập nhật | `POST /v1/kv/apps/orders/order-001` | `POST /v1/kv/data/apps/orders/order-001` | `create` / `update` theo tình huống |
| Liệt kê khóa | `LIST /v1/kv/apps/orders` | `LIST /v1/kv/metadata/apps/orders` | `list` trên path được liệt kê |
| Xóa giá trị | `DELETE /v1/kv/apps/orders/order-001` | `DELETE /v1/kv/data/apps/orders/order-001` | `delete` |
| Đọc metadata phiên bản | Không có endpoint tương đương KV v2 | `GET /v1/kv/metadata/apps/orders/order-001` | `read`, nếu thực sự dùng |

Chú ý: `DELETE` trên endpoint `data` của KV v2 thường thực hiện **soft delete phiên bản mới nhất**; xóa hẳn lịch sử dùng các endpoint khác và quyền khác. Không cấp quyền với `destroy`, `undelete` hay các endpoint quản lý phiên bản khi repository không có nghiệp vụ tương ứng.

Với KV v2, ACL bảo vệ **API path thực** (`data` / `metadata`), trong khi khi dùng Spring Vault ta thường truyền **đường dẫn logic** không chứa những đoạn này. Tự chèn `data/` vào key logic hoặc áp dụng policy KV v1 cho KV v2 đều có thể gây 403 hoặc 404 khó hiểu.

## 4. Policy tối thiểu cho một repository KV v2

Giả sử Spring Vault được cấu hình rõ mount `kv` và ứng dụng chỉ sở hữu key dưới `apps/orders/`. Policy cho repository **chỉ đọc theo ID** có thể bắt đầu như sau:

~~~hcl
# orders-repository-read.hcl
path "kv/data/apps/orders/*" {
  capabilities = ["read"]
}
~~~

Nếu repository phải tạo và cập nhật object:

~~~hcl
# orders-repository-write.hcl
path "kv/data/apps/orders/*" {
  capabilities = ["create", "read", "update"]
}
~~~

Nếu ứng dụng gọi `deleteById` hoặc thao tác xóa tương đương, bổ sung `delete` **trên chính phạm vi `data`**. Nếu thực hiện `findAll` hoặc phải liệt kê tên khóa, bổ sung riêng `list` cho metadata:

~~~hcl
# Chỉ bổ sung khi repository thực sự cần liệt kê khóa.
# Có cả đường dẫn thư mục và các cấp con nếu cần duyệt lồng nhau.
path "kv/metadata/apps/orders" {
  capabilities = ["list"]
}

path "kv/metadata/apps/orders/*" {
  capabilities = ["list"]
}
~~~

Một số thư viện cần đọc metadata của **một khóa cụ thể** để phục vụ xử lý phiên bản. Chỉ trong trường hợp đó mới bổ sung `read` trên `kv/metadata/apps/orders/*`; không suy ra rằng `read` metadata là bắt buộc cho mọi `get` của KV v2.

Điểm cần cân nhắc với `list`: việc liệt kê trả về **tên khóa**, và danh sách không được Vault tự lọc xuống từng key theo ACL đọc giá trị. Vì vậy hãy phân chia đường dẫn theo workload/tenant và hạn chế cấp `list` trên thư mục chung. Quyền đọc value và quyền xem tên các key là hai quyết định bảo mật độc lập.

Không sử dụng policy quá rộng như:

~~~hcl
# Không áp dụng cho workload thông thường.
path "sys/*" {
  capabilities = ["read", "list", "sudo"]
}

path "kv/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
~~~

Những quyền này mở rộng đáng kể phạm vi của token so với nhu cầu của một repository đơn lẻ.

## 5. Đường đi từ VaultRepository đến mount

Sơ đồ sau minh họa các nhánh có thể xảy ra. **Nhánh khám phá là tùy cấu hình và phiên bản client**, không phải chuỗi HTTP bắt buộc của mọi repository.

~~~mermaid
flowchart TD
    A["Java service / repository"] --> B["Spring Vault: VaultTemplate / KV operations"]
    B --> C{"Đã biết chính xác mount và KV version?"}
    C -->|Có| D["Xây dựng URL KV v1 hoặc KV v2"]
    C -->|Chưa| E["Khám phá mount / nhận diện backend (nếu client hỗ trợ)"]
    E --> D
    D --> F{"Thao tác repository"}
    F -->|Đọc / ghi| G["API dữ liệu: KV v2 /data/..."]
    F -->|Liệt kê| H["API metadata: KV v2 /metadata/..."]
    G --> I["Vault kiểm tra ACL của token"]
    H --> I
    I --> J["Kết quả hoặc lỗi 403 / 404"]
~~~

Ví dụ Java thao tác KV v2 với backend được chỉ rõ (dành cho những luồng sử dụng `VaultTemplate`):

~~~java
import java.util.Map;

import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultTemplate;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.support.VaultResponse;

public class OrderSecretStore {

    private final VaultKeyValueOperations ordersKv;

    public OrderSecretStore(VaultTemplate vaultTemplate) {
        this.ordersKv = vaultTemplate.opsForKeyValue("kv", KeyValueBackend.KV_2);
    }

    public void save(String orderId, String state) {
        ordersKv.put("apps/orders/" + orderId, Map.of("state", state));
    }

    public VaultResponse find(String orderId) {
        return ordersKv.get("apps/orders/" + orderId);
    }
}
~~~

Ở ví dụ này:

1. `kv` là tên mount. `KV_2` nói rõ kiểu API cần dùng.
2. `apps/orders/` là prefix dữ liệu, **không** phải mount mới.
3. Policy cho `save` cần `create` hoặc `update` trên `kv/data/apps/orders/*`; `find` cần `read`.
4. Đoạn mã minh họa thao tác KV tương ứng với repository; khi dùng interface repository / ánh xạ entity, phải kiểm tra cấu hình backend và các phương thức mà implementation thực sự gọi.

**An toàn dữ liệu:** `orderId` nên được kiểm tra định dạng (chẳng hạn chỉ ký tự chữ, số và dấu gạch nối) trước khi ghép vào Vault path. Không đưa chuỗi tùy ý của người dùng vào prefix có thể gây truy cập ngoài phạm vi mong đợi.

## 6. Chứng minh chính xác quyền mà workload cần

Hãy kiểm tra bằng **token và namespace của workload** (ví dụ token do Kubernetes auth hoặc AppRole cấp), thay vì token root của người vận hành. Trong môi trường thử nghiệm, quản trị viên bật mount KV v2 một lần:

~~~bash
# Chỉ tài khoản vận hành đủ quyền mới thực hiện phần này.
vault secrets enable -path=kv -version=2 kv

vault policy write orders-repository-write orders-repository-write.hcl
~~~

Sau khi workload đã đăng nhập bằng phương thức xác thực thực tế và có `VAULT_ADDR`, `VAULT_TOKEN` phù hợp:

~~~bash
# Đang dùng chính token workload cần kiểm tra.
vault token capabilities kv/data/apps/orders/order-001
vault token capabilities kv/metadata/apps/orders

# Kiểm tra theo đường dẫn logic, Vault CLI tự ánh xạ KV v2.
vault kv put -mount=kv apps/orders/order-001 state=CREATED
vault kv get -mount=kv apps/orders/order-001

# Chỉ chạy nếu nghiệp vụ thực sự cần list và policy đã cấp list.
vault kv list -mount=kv apps/orders/
~~~

Kết quả mong đợi: capability cho `data` phù hợp hành động đọc/ghi; capability cho `metadata/apps/orders` chỉ có `list` nếu đã chủ động cấp. `vault token capabilities` xác nhận quyền theo path, trong khi lệnh `vault kv` xác nhận cả quyền, mount, phiên bản và cách gọi API. Nếu khóa chưa tồn tại, phép đọc trả không tìm thấy dữ liệu vẫn có thể là hành vi đúng; hãy ghi một bản ghi thử trước khi đánh giá luồng đọc.

Nếu workload chỉ có chức năng đọc, đừng kiểm thử quyền ghi bằng token đó rồi xem lỗi từ chối là thất bại: **lỗi 403 trên thao tác không được cấp quyền chính là kiểm tra phân quyền thành công**.

Có thể dùng token admin để xem cấu hình mount bằng `vault secrets list -detailed`. Đây là bước chẩn đoán phía vận hành; kết quả không tạo lý do để cấp `sys/mounts` cho ứng dụng.

## 7. Khi preflight mount trả 403: tìm nguyên nhân theo thứ tự

Lỗi thường có dạng `permission denied` khi client đang nhận diện mount, hoặc `permission denied` khi thao tác KV. Không nên chỉ nhìn chuỗi ngoại lệ rồi kết luận thiếu quyền trên `sys/internal/ui/mounts`.

| Hiện tượng | Khả năng đáng kiểm tra | Cách xác minh và sửa |
|---|---|---|
| 403 tại preflight mount | Token không có quyền ở đường dẫn secrets mục tiêu, token/namespace không đúng, hoặc cơ chế khám phá client không tương thích | Đối chiếu HTTP request thực tế và capability của token trên `kv/data/...`; kiểm tra namespace, mount và phiên bản |
| 403 khi GET `.../data/...` | Thiếu `read` trên dữ liệu KV v2 hoặc policy đang viết cho KV v1 | Dùng `vault token capabilities` với URL path thực; sửa ACL đúng `data` |
| 403 khi LIST `.../metadata/...` | Chưa cấp `list` cho thư mục được liệt kê | Chỉ cấp `list` cho đúng prefix cần duyệt; xác minh repository có thật sự cần liệt kê |
| 404 / no handler for route | Sai tên mount, KV version, path hoặc route API | Kiểm tra `kv` có là mount thực không; so sánh KV v1 `/<key>` với KV v2 `/data/<key>` |
| CLI chạy được bằng root, Java thất bại | CLI và service dùng token, namespace hoặc URL khác nhau | Kiểm thử cả hai với cùng workload identity, namespace và backend |
| Quyền hoạt động rồi đột ngột mất | Token bị thu hồi, hết TTL; auth role thay đổi hoặc Vault policy thay đổi | Kiểm tra vòng đời token/renewal, policy gán cho role và thời điểm lỗi; không tăng quyền để chữa lỗi hết hạn |

Quy trình xử lý thực tế:

1. **Xác định danh tính:** workload đăng nhập bằng auth method nào (Kubernetes, AppRole, v.v.), token thuộc namespace nào và có policy nào? Không in token vào log.
2. **Xác định đích:** mount là `kv` hay một tên khác? KV v1 hay v2? Repository đang truy cập key nào dưới prefix nào?
3. **Quan sát yêu cầu thực:** ghi lại HTTP method, path đã loại bỏ dữ liệu nhạy cảm, status code và Vault request ID; dùng audit log của Vault nếu có quyền vận hành.
4. **Kiểm chứng capability:** đối chiếu path thực với từng policy, đặc biệt cặp `data` / `metadata` của KV v2.
5. **Sửa đúng tầng:** sửa path/backend khi client gọi sai; bổ sung quyền dữ liệu tối thiểu khi thật sự thiếu; xử lý token TTL/auth khi token không còn hợp lệ.
6. **Thử lại các thao tác cần thiết:** `get`, `put`, `list` và `delete` tùy repository; đồng thời xác nhận thao tác ngoài phạm vi tiếp tục bị từ chối.

Một phản hồi 403 ở endpoint khám phá có thể cố ý che giấu thông tin tồn tại của mount. Đừng suy ra chắc chắn rằng mount không tồn tại chỉ từ mã trạng thái đó.

## 8. Tách quyền khám phá, quyền dữ liệu và vòng đời token

Spring Vault có thể được cấp token bằng phương thức xác thực dành cho workload, chẳng hạn Kubernetes auth hoặc AppRole. **Auth policy quyết định workload có thể làm gì; phương thức đăng nhập quyết định workload nhận token thế nào.** Cả hai khác với câu hỏi client có cần khám phá mount hay không.

Với dịch vụ Java chạy dài hạn:

- Gắn policy giới hạn vào role của workload, không đặt token root trong cấu hình hay mã nguồn.
- Giữ TTL/renewal của token phù hợp thời gian chạy; kiểm tra việc cấp lại token khi workload restart và điều kiện revocation.
- Phân biệt KV static secrets với dynamic credentials có lease. Thao tác KV đọc/ghi không đồng nghĩa tạo một lease động cần gia hạn.
- Khi dùng Vault Enterprise namespace, so sánh cùng namespace ở cấu hình Spring Vault, token và lệnh thử nghiệm; cùng tên mount ở namespace khác nhau có thể trỏ tới engine khác nhau.
- Giới hạn lộ bí mật trong ứng dụng: log đường dẫn đã làm sạch, status và correlation ID; không log secret value, token, AppRole SecretID hoặc response body nhạy cảm.

Những việc này ảnh hưởng khả năng repository hoạt động ổn định và an toàn, nhưng **không được giải quyết bằng một ACL toàn quyền trên `sys/*`**.

## 9. Bài thực hành: ma trận quyền theo hành vi repository

Giả sử repository quản lý khóa dưới `kv/apps/orders/` (nghĩa là mount `kv`, prefix nội bộ `apps/orders/`). Hãy xây dựng và kiểm chứng ba vai trò:

| Vai trò workload | Nghiệp vụ được phép | Policy KV v2 cần thiết | Kiểm tra âm tính |
|---|---|---|---|
| Reader | Tìm object theo ID | `read` trên `kv/data/apps/orders/*` | `put` và `delete` phải bị từ chối |
| Writer | Tạo, sửa, đọc object theo ID | `create`, `update`, `read` trên `kv/data/apps/orders/*` | `list` trên `kv/metadata/apps/orders` phải bị từ chối nếu không cấp |
| Browser | Đọc và liệt kê object | `read` trên `kv/data/apps/orders/*`, `list` trên metadata của prefix | Không thể xem dữ liệu của `apps/payments/*` |

Thực hiện theo trình tự: tạo policy, gán vào auth role thử nghiệm, đăng nhập để nhận token giới hạn, thực hiện lệnh CLI và luồng Java tương ứng, sau đó kiểm chứng các thao tác bị từ chối. Nên dùng instance Vault dành cho tích hợp hoặc môi trường phát triển được cô lập.

Một integration test hữu ích cần xác nhận **hai phía của ranh giới quyền**: các thao tác đúng nhiệm vụ đều thành công và các thao tác ngoài phạm vi đều bị từ chối. Ví dụ, sau khi Reader đọc được `apps/orders/order-001`, thử đọc `apps/payments/payment-001` phải thất bại. Khi kiểm tra LIST, dùng đúng metadata prefix thay vì suy diễn từ quyền GET. Nếu thay đổi backend KV v1 ↔ KV v2, cập nhật cả cấu hình Java lẫn đường dẫn ACL trước khi chạy lại.

## 10. Checklist trước khi đưa Vault Repository vào sử dụng

- [ ] Ghi rõ mount của workload (`kv`), phiên bản KV và prefix logic của repository.
- [ ] Kiểm tra cơ chế Spring Vault đang dùng: cấu hình backend tường minh hay có bước khám phá mount.
- [ ] Liệt kê các hành vi repository thực sự gọi: đọc, ghi, xóa, liệt kê và đọc metadata.
- [ ] Cấp `read/create/update/delete` đúng `data` và `list/read` đúng `metadata` khi dùng KV v2.
- [ ] Không cấp `sys/mounts` hoặc `sys/*` cho workload chỉ để chữa lỗi preflight.
- [ ] Thử với token được cấp bởi auth role thực tế, cùng namespace và TTL phù hợp.
- [ ] Kiểm tra cả yêu cầu được phép lẫn yêu cầu phải bị từ chối; xem audit log khi điều tra 403.
- [ ] Không ghi token, giá trị secrets và nội dung phản hồi nhạy cảm vào log.

## 11. Kết luận

Đối với Spring Vault Repository, quyền cần thiết để làm việc với mount phụ thuộc vào **cách client nhận diện engine** và **những thao tác dữ liệu mà repository thực hiện**. Với KV v2, phần lớn quyền nghiệp vụ nằm ở `<mount>/data/<prefix>` và `<mount>/metadata/<prefix>`. Endpoint khám phá nội bộ và quyền quản trị `sys/mounts` thuộc hai cơ chế khác nhau; không thể coi `read` trên `sys/*` là điều kiện mặc định của CRUD repository.

Thiết kế tốt nhất là cấu hình chính xác mount và phiên bản engine, thử policy với danh tính workload, cấp capability theo thao tác thực tế và bảo đảm test xác nhận cả quyền cho phép lẫn quyền từ chối. Nhờ vậy Java có thể truy cập Vault qua `VaultTemplate` hoặc lớp repository mà vẫn giữ được nguyên tắc ít quyền nhất.
