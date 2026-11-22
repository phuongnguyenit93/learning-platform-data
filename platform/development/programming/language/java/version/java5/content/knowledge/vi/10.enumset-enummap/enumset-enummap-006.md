# Dùng EnumSet để mô hình hóa tập quyền hoặc tập tùy chọn

## 1. Khi dữ liệu là một nhóm lựa chọn trong một miền hữu hạn

Giả sử một tác vụ có thể được đọc, chỉnh sửa, xuất dữ liệu hoặc xóa. Một đối tượng có thể có nhiều quyền cùng lúc, nên một biến enum đơn lẻ chưa đủ mô tả tình huống:

```java
enum Permission {
    READ, WRITE, EXPORT, DELETE
}
```

`EnumSet<Permission>` biểu diễn một **tập các quyền** thuộc miền `Permission`:

```java
java.util.EnumSet<Permission> granted = java.util.EnumSet.of(
        Permission.READ, Permission.EXPORT);
```

Tập này nói rằng hai quyền đang hiện diện. Nó không nói phải chọn đúng một quyền, không giữ quyền trùng lặp và không gắn một giá trị cấu hình tùy ý vào mỗi quyền.

Mô hình tương tự áp dụng cho các tùy chọn bật/tắt của một thao tác. Bài này dùng kiến thức và API còn áp dụng trong Java hiện hành; chương trình đầy đủ chạy bằng Java 17 trở lên.

## 2. Vì sao một tập enum phù hợp hơn nhiều boolean rời rạc trong trường hợp này?

Khi các lựa chọn cùng một khái niệm và thường được truyền, sao chép hoặc kiểm tra theo nhóm, một tập có tên kiểu làm hợp đồng rõ hơn:

```java
EnumSet<Permission> reader = EnumSet.of(Permission.READ);
EnumSet<Permission> editor = EnumSet.of(Permission.READ, Permission.WRITE);
EnumSet<Permission> none = EnumSet.noneOf(Permission.class);
```

Các câu lệnh trên cần đặt trong một phương thức có import `java.util.EnumSet` và dùng enum `Permission` đã khai báo.

Ưu điểm về mô hình:

- Tập rỗng diễn đạt “không có lựa chọn nào” mà không cần null.
- Tên hằng cho biết ý nghĩa, không cần nhớ vị trí của từng bit hoặc từng đối số boolean.
- Một kiểu `EnumSet<Permission>` không nhận tùy tiện hằng của enum tùy chọn khác.
- Có sẵn phép kiểm tra thành viên và các phép tập hợp để diễn đạt chính sách nhóm.

`EnumSet` được triển khai chuyên biệt cho enum, nhưng không cần phụ thuộc vào lớp nội bộ hoặc cách đánh số bit để dùng API. Ý nghĩa nghiệp vụ nên được diễn đạt bằng hằng enum, không bằng `ordinal()`.

Không phải mọi cấu hình đều là một tập cờ. Nếu mỗi lựa chọn cần một giá trị riêng, như độ nén hoặc giới hạn số dòng, cần thêm một mô hình giá trị phù hợp. `EnumSet` chỉ biểu diễn việc một thành viên có mặt hay không.

## 3. Kiểm tra một quyền, tất cả quyền và ít nhất một quyền

### Một quyền: contains

```java
boolean canRead = granted.contains(Permission.READ);
```

`contains` trả lời một câu hỏi thành viên. Nó không tự suy ra quyền khác: có `WRITE` không mặc nhiên có `READ` trừ khi chương trình đã xây dựng rõ quy tắc suy diễn đó.

### Tất cả quyền bắt buộc: containsAll

```java
EnumSet<Permission> required = EnumSet.of(Permission.READ, Permission.WRITE);
boolean canEdit = granted.containsAll(required);
```

Kết quả đúng khi mọi thành viên của `required` đều có trong `granted`. Nếu thiếu `WRITE`, chỉ có `READ` không đủ để thao tác trong ví dụ được chấp nhận.

### Ít nhất một quyền thay thế: kiểm tra giao không rỗng

```java
EnumSet<Permission> alternatives = EnumSet.of(Permission.EXPORT, Permission.DELETE);
boolean hasAny = !java.util.Collections.disjoint(granted, alternatives);
```

`Collections.disjoint` trả `true` khi hai tập không có phần tử chung. Phủ định của nó diễn đạt “có ít nhất một thành viên chung”. Có thể viết vòng lặp và dừng khi tìm được một quyền phù hợp; không cần sửa tập để trả lời câu hỏi này.

Phân biệt yêu cầu rất quan trọng: `containsAll` và “có bất kỳ” không thể thay thế cho nhau chỉ vì cùng nhận một tập quyền.

### Tập yêu cầu rỗng có kết quả toán học riêng

- `granted.containsAll(empty)` là `true`: không có yêu cầu nào đang bị thiếu.
- “Có ít nhất một quyền trong empty” là `false`: không có lựa chọn nào để đáp ứng.

Nếu một API nghiệp vụ yêu cầu danh sách điều kiện phải có ít nhất một phần tử, kiểm tra điều đó riêng. Đừng dựa vào tên hàm như `canEdit` để giả định tập đầu vào rỗng tự bị từ chối.

## 4. Các phép tập hợp giúp xây dựng lựa chọn

Những phương thức như `addAll`, `retainAll`, `removeAll` **thay đổi tập nhận lời gọi**. Khi cần tính một tập kết quả mà giữ nguyên nguồn, tạo bản sao trước:

```java
EnumSet<Permission> base = EnumSet.of(Permission.READ);
EnumSet<Permission> extra = EnumSet.of(Permission.WRITE, Permission.EXPORT);

EnumSet<Permission> combined = base.clone();
combined.addAll(extra);
```

`combined` có `READ`, `WRITE`, `EXPORT`; `base` vẫn chỉ có `READ`.

| Ý định | Cách tính trên một bản sao |
| --- | --- |
| Hợp hai nhóm | `result.addAll(other)` |
| Chỉ giữ quyền có ở cả hai nhóm | `result.retainAll(other)` |
| Bỏ các quyền trong nhóm bị loại | `result.removeAll(other)` |
| Tìm quyền còn thiếu | Sao chép tập bắt buộc, rồi `removeAll(granted)` |

Giá trị boolean trả về của các thao tác sửa tập cho biết **tập có thay đổi hay không**; nó không phải chính tập kết quả. Ví dụ, `retainAll` trả `false` cũng có thể vì tập đã đúng bằng giao cần giữ ngay từ đầu, không phải vì giao chắc chắn rỗng.

Với quyền truy cập, phép hợp hoặc phép trừ chỉ là thao tác dữ liệu. Việc nhóm nào được hợp, quyền từ chối nào cần ưu tiên hay điều kiện tài nguyên nào phải kiểm tra là quy tắc riêng, không tự xuất hiện từ `EnumSet`.

## 5. Bảo vệ quyền sở hữu dữ liệu khi truyền tập

Một `EnumSet` thông thường có thể thay đổi. Nếu giữ nguyên tập mà bên gọi truyền vào, bên gọi có thể sửa nguồn và làm đổi trạng thái mà đối tượng đang dùng.

```java
EnumSet<Permission> source = EnumSet.of(Permission.READ);
EnumSet<Permission> alias = source;
alias.add(Permission.DELETE);
```

`source` giờ cũng có `DELETE` vì hai biến giữ cùng một tham chiếu. `final` trên biến trường chỉ ngăn gán lại tham chiếu, không ngăn thêm/xóa phần tử của tập.

Một lựa chọn rõ ràng là tạo **bản chụp thành viên** khi xây dựng hồ sơ quyền:

```java
EnumSet<Permission> snapshot = source.clone();
```

`clone()` của `EnumSet` trả về một `EnumSet` cùng kiểu phần tử, có cùng thành viên ban đầu, kể cả khi nguồn rỗng. Sửa thành viên của bản chụp không sửa nguồn và ngược lại.

Đây là sao chép tập thành viên, không phải sao chép sâu mọi dữ liệu có thể nằm trong các hằng enum. Trong mô hình của bài, các hằng không chứa trạng thái thay đổi.

Khi trả dữ liệu ra ngoài, có thể cung cấp `Set<Permission>` không cho sửa bằng `Collections.unmodifiableSet`. Lưu ý đây là **góc nhìn** của tập được bọc; nếu mã sở hữu tập bên trong còn sửa nó, góc nhìn sẽ phản ánh thay đổi ấy. Muốn một hồ sơ ổn định, phải kết hợp bản sao đầu vào với việc không thay đổi tập riêng bên trong và không làm lộ tham chiếu có thể sửa.

## 6. Chương trình chạy đầy đủ: hồ sơ quyền có bản chụp

Lưu thành **`EnumSetPolicyDemo.java`**:

```java
import java.util.Collections;
import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;

public class EnumSetPolicyDemo {
    enum Permission {
        READ, WRITE, EXPORT, DELETE
    }

    static final class PermissionProfile {
        private final EnumSet<Permission> granted;

        PermissionProfile(EnumSet<Permission> granted) {
            this.granted = Objects.requireNonNull(granted, "granted").clone();
        }

        boolean allows(Permission permission) {
            return granted.contains(Objects.requireNonNull(permission, "permission"));
        }

        boolean allowsAll(EnumSet<Permission> required) {
            return granted.containsAll(Objects.requireNonNull(required, "required"));
        }

        boolean allowsAny(EnumSet<Permission> alternatives) {
            Objects.requireNonNull(alternatives, "alternatives");
            return !Collections.disjoint(granted, alternatives);
        }

        Set<Permission> view() {
            return Collections.unmodifiableSet(granted);
        }
    }

    public static void main(String[] args) {
        EnumSet<Permission> source = EnumSet.of(Permission.READ, Permission.EXPORT);
        PermissionProfile profile = new PermissionProfile(source);
        System.out.println("granted=" + profile.view());
        System.out.println("read=" + profile.allows(Permission.READ));
        System.out.println("edit=" + profile.allowsAll(
                EnumSet.of(Permission.READ, Permission.WRITE)));
        System.out.println("any output=" + profile.allowsAny(
                EnumSet.of(Permission.EXPORT, Permission.DELETE)));

        EnumSet<Permission> empty = EnumSet.noneOf(Permission.class);
        System.out.println("all empty=" + profile.allowsAll(empty));
        System.out.println("any empty=" + profile.allowsAny(empty));

        source.add(Permission.DELETE);
        System.out.println("snapshot has delete=" + profile.allows(Permission.DELETE));

        EnumSet<Permission> missing = EnumSet.of(Permission.READ, Permission.WRITE);
        missing.removeAll(profile.view());
        System.out.println("missing=" + missing);

        try {
            profile.view().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("view modification rejected");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all EnumSetPolicyDemo.java
java EnumSetPolicyDemo
```

Stdout chính xác:

```text
granted=[READ, EXPORT]
read=true
edit=false
any output=true
all empty=true
any empty=false
snapshot has delete=false
missing=[WRITE]
view modification rejected
```

Chương trình dùng phép kiểm tra khác nhau cho các yêu cầu khác nhau. Tập `source` được thêm `DELETE` sau khi tạo hồ sơ, nhưng bản chụp riêng của `profile` không đổi. Phần `missing` tính tập thiếu trên một tập mới, không trừ trực tiếp khỏi hồ sơ đang có.

`view()` giữ nguyên thứ tự duyệt của `EnumSet` bên trong, nên kết quả in theo thứ tự khai báo enum. Thứ tự ấy phục vụ việc duyệt và hiển thị; nó không tạo mức độ ưu tiên hoặc quan hệ “quyền cao hơn” giữa các hằng.

## 7. Áp dụng cùng mô hình cho tập tùy chọn

Ví dụ, một thao tác xuất báo cáo có các tùy chọn bật/tắt độc lập:

```java
enum ExportOption {
    INCLUDE_HEADER, INCLUDE_TOTALS, COMPRESS
}
```

Trong phương thức thực hiện thao tác, có thể tạo nhóm lựa chọn:

```java
EnumSet<ExportOption> options = EnumSet.of(
        ExportOption.INCLUDE_HEADER, ExportOption.INCLUDE_TOTALS);
boolean includeHeader = options.contains(ExportOption.INCLUDE_HEADER);
boolean compress = options.contains(ExportOption.COMPRESS);
```

Tập rỗng là “không bật tùy chọn nào”; một cấu hình mặc định có thể được biểu diễn bằng một nhóm hằng rõ ràng. Nếu cần giữ cấu hình mặc định dùng chung, không trao trực tiếp một `EnumSet` có thể sửa cho bên gọi.

Một tùy chọn có tên không tự triển khai hành vi. `COMPRESS` có mặt chỉ là dữ liệu cho biết ý định; mã xử lý vẫn phải thực hiện việc nén khi tùy chọn được bật. Tương tự, nếu hai tùy chọn không tương thích, cần kiểm tra điều kiện ấy riêng vì `EnumSet` chỉ kiểm tra kiểu phần tử, không biết quy tắc phối hợp của nghiệp vụ.

Nếu một lựa chọn có nhiều mức loại trừ nhau, như `LOW`, `MEDIUM`, `HIGH`, một biến enum duy nhất có thể phù hợp hơn một tập cho phép bật cả ba. Chọn mô hình theo số lựa chọn được phép xuất hiện đồng thời.

## 8. Tập quyền không phải toàn bộ cơ chế phân quyền

`EnumSet<Permission>` mô tả dữ liệu thành viên và hỗ trợ các câu hỏi về tập. Nó không tự xác thực người dùng, xác định nguồn cấp quyền đáng tin, kiểm tra chủ sở hữu một tài nguyên hay thực thi quyết định tại nơi thao tác thật diễn ra.

Trong một ứng dụng, tập quyền cần đến từ nguồn và ngữ cảnh phù hợp. Các điều kiện như phạm vi tài nguyên, vai trò, chính sách từ chối hoặc thời điểm hiệu lực cần được mô hình hóa và kiểm tra theo yêu cầu thật. Không xem một tập do phía gọi tùy ý gửi tới là bằng chứng tự thân rằng thao tác đã được phép.

Đây là giới hạn của ví dụ mô hình dữ liệu: `PermissionProfile` cho thấy cách giữ và hỏi tập quyền, không phải một framework bảo mật đầy đủ. Đặt tên và tài liệu của API sao cho phạm vi bảo đảm này rõ ràng.

## 9. Chọn tập mặc định và dữ liệu lưu trữ có chủ đích

### allOf có thể mở rộng ý nghĩa khi thêm hằng

`EnumSet.allOf(Permission.class)` có nghĩa mọi quyền trong định nghĩa enum được dùng. Nếu một quyền mới xuất hiện trong phiên bản sau, tập “tất cả” cũng bao gồm quyền đó khi được tạo với định nghĩa mới.

Vì vậy, dùng `allOf` chỉ khi ý định thật sự là mọi lựa chọn, không coi nó như cách viết ngắn mặc định cho một nhóm đã được duyệt trước. `of` liệt kê nhóm cụ thể giúp thể hiện một hợp đồng khác.

### Thứ tự khai báo không phải mã lưu trữ ổn định

Không lưu tập quyền bằng các `ordinal` tự suy diễn rồi coi thứ tự enum không bao giờ đổi. Nếu cần trao đổi hoặc lưu trữ, chọn tên/mã ổn định và chính sách cho mã không biết theo hợp đồng dữ liệu. Cách biểu diễn bit nội bộ của `EnumSet` không phải một định dạng giao tiếp nghiệp vụ mà mã ứng dụng cần dựa vào.

### Tránh sửa tập đang được nhiều nơi chia sẻ

Những thao tác `retainAll` hoặc `removeAll` để “kiểm tra” có thể vô tình làm mất quyền nếu nhận trực tiếp tập nguồn. Nếu chỉ cần một boolean, dùng `contains`, `containsAll` hoặc kiểm tra giao. Nếu cần tập kết quả, tính trên một bản sao được sở hữu riêng.

## 10. Những lỗi thường gặp

| Lỗi | Hệ quả hoặc cách sửa |
| --- | --- |
| Dùng một enum đơn lẻ cho nhiều quyền đồng thời | Không diễn đạt được tập; dùng `EnumSet` khi cần nhiều thành viên |
| Nhầm `containsAll` với có ít nhất một | Chấp nhận hoặc từ chối sai yêu cầu; đặt rõ điều kiện all/any |
| Coi tập yêu cầu rỗng tự bị từ chối | `containsAll(empty)` vẫn đúng; xác minh điều kiện nghiệp vụ riêng |
| Dùng thao tác sửa tập để kiểm tra rồi quên sao chép | Thay đổi dữ liệu nguồn ngoài ý muốn |
| Coi `final EnumSet` là tập bất biến | Nội dung vẫn thêm/xóa được |
| Tưởng unmodifiable view là bản sao độc lập | Thay đổi nguồn có thể xuất hiện qua góc nhìn |
| Tự suy ra WRITE kéo theo READ | Cần quy tắc riêng nếu quan hệ ấy là yêu cầu của miền |
| Bật toàn bộ tùy chọn mà không kiểm tra xung đột | Tập hợp lệ về kiểu vẫn có thể không hợp lệ về nghiệp vụ |

## 11. Tự thực hành

1. Tạo ba hồ sơ: không quyền, chỉ đọc, đọc và ghi. Kiểm tra `allows`, `allowsAll`, `allowsAny` với cùng một tập yêu cầu và giải thích các kết quả khác nhau.
2. Tính tập quyền còn thiếu của một thao tác yêu cầu `READ`, `WRITE`, `EXPORT` mà không sửa hồ sơ gốc.
3. Sửa tập nguồn sau khi tạo `PermissionProfile` và xác nhận bản chụp không đổi. Sau đó giải thích khác biệt nếu constructor giữ trực tiếp tham chiếu nguồn.
4. Viết điều kiện bắt buộc tập `required` không rỗng trước khi kiểm tra tất cả, nếu đó là quy tắc API bạn chọn.
5. Mô hình hóa tùy chọn của một báo cáo, xác định tùy chọn độc lập và lựa chọn phải loại trừ nhau. Chỉ dùng tập cho những nhóm thực sự được phép đồng thời có nhiều thành viên.

`EnumSet` giúp biến nhiều lựa chọn có tên thành một tập có kiểu rõ ràng. Để mô hình đó đúng, cần xác định ngữ nghĩa all/any, bảo vệ quyền sở hữu tập và giữ riêng các quy tắc nghiệp vụ mà collection không tự biết.

## Tài liệu đối chiếu

- [EnumSet — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html): kiểu phần tử, bản sao, thứ tự và thao tác tập hợp cho enum.
- [Collection.containsAll](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html#containsAll(java.util.Collection)): điều kiện chứa toàn bộ phần tử.
- [Collections.disjoint](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#disjoint(java.util.Collection,java.util.Collection)): kiểm tra không có phần tử chung.
- [Collections.unmodifiableSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set)): góc nhìn tập không cho sửa và quan hệ với tập nguồn.
