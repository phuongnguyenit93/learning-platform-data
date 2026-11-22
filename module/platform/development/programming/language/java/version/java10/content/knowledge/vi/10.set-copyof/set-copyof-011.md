# Sử dụng `Set.copyOf` để tạo bản sao tập cho danh mục giá trị hoặc quyền hạn

*Chủ đề Java 10 — `Set.copyOf`. Bài học tập trung vào các API và quy tắc vẫn áp dụng trong Java 17+ và các JDK hiện đại. Mục tiêu là tạo một tập giá trị đã được kiểm tra, không cho người nhận sửa qua API của tập, và hiểu rõ giới hạn của “bản sao” khi dùng trong danh mục cấu hình hoặc phân quyền.*

## 1. Ý tưởng chính và trường hợp sử dụng

`Set.copyOf(Collection<? extends E> source)` tạo một `Set<E>` **không thể sửa** (*unmodifiable set*) từ các phần tử của một collection nguồn. Đây là công cụ phù hợp khi ta cần **xuất bản một tập giá trị** được chuẩn bị từ nguồn có thể thay đổi, chẳng hạn:

- Danh mục mã sản phẩm hoặc loại dịch vụ hợp lệ: `BASIC`, `PLUS`, `PRO`.
- Tập các tính năng được bật cho một cấu hình.
- Danh sách loại sự kiện mà một thành phần có thể xử lý.
- Tập quyền hiệu lực của một người dùng hoặc một vai trò **tại một thời điểm xác định**.

Ví dụ ngắn:

~~~java
var rawCodes = new ArrayList<>(List.of("BASIC", "PLUS"));
Set<String> allowedCodes = Set.copyOf(rawCodes);

rawCodes.add("INTERNAL");
// allowedCodes vẫn chỉ chứa BASIC, PLUS.

// allowedCodes.add("ADMIN"); // Biên dịch được, ném UnsupportedOperationException.
~~~

Ý nghĩa: sau khi nhận `allowedCodes`, mã tiêu thụ không thể thêm/xóa phần tử qua tham chiếu này. Nếu `rawCodes` được thay đổi **sau thời điểm tạo copy**, kết quả `allowedCodes` không tự cập nhật. Đây là điểm cần hiểu thật kỹ, đặc biệt khi bản sao đại diện cho **quyền truy cập**.

`Set.copyOf` có từ **Java 10**, vẫn được duy trì trong Java hiện hành. Có thể dùng `var published = Set.copyOf(rawCodes);` cho biến cục bộ, nhưng kiểu của biến vẫn là kiểu tĩnh `Set<String>`. `var` không thay đổi hành vi hay quyền sửa của collection.

## 2. Hợp đồng API cần nhớ trước khi ứng dụng

`Set.copyOf` có các đặc điểm chủ yếu:

1. **Không thể sửa tập kết quả:** gọi `add`, `remove`, `clear` hoặc các đường sửa đổi khác trên kết quả sẽ không thực hiện được (các mutator không được hỗ trợ).
2. **Từ chối `null`:** collection nguồn không được `null`, và không được chứa phần tử `null`; nếu vi phạm, phương thức ném `NullPointerException`.
3. **Loại phần tử trùng theo ngữ nghĩa của set:** nếu nguồn là `List` có nhiều phần tử bằng nhau theo `equals`, kết quả chỉ có một phần tử cho mỗi nhóm giá trị bằng nhau.
4. **Không bảo đảm thứ tự duyệt:** đừng dựa vào thứ tự được truyền vào hoặc thứ tự in từ `toString()`. Nếu cần hiển thị có thứ tự, hãy sắp xếp một bản trình bày riêng.
5. **Không phản ánh các thao tác thêm, xóa hay thay thế phần tử về sau ở collection nguồn**. Đây là điểm khác biệt với một *read-only view* trên backing collection.
6. **Không sao chép sâu đối tượng phần tử:** nếu phần tử tự nó có thể thay đổi, trạng thái bên trong phần tử có thể thay đổi dù tập không thể thêm/xóa phần tử.
7. **Không cam kết luôn tạo một object mới:** khi nguồn đã là unmodifiable set phù hợp, implementation có thể tái sử dụng nguồn. Đừng dựa vào `==`, danh tính hay cách phân bổ bộ nhớ.

Ví dụ về trùng lặp:

~~~java
var raw = List.of("BASIC", "BASIC", "PLUS");
var codes = Set.copyOf(raw); // size() == 2
~~~

Ở đây, `Set.copyOf` không báo lỗi vì danh sách nguồn có hai chuỗi giống nhau. Nhưng:

~~~java
// Dòng sau ném IllegalArgumentException lúc chạy:
var codes = Set.of("BASIC", "BASIC");
~~~

`Set.of` **khác** `Set.copyOf` ở trường hợp đối số trùng nhau: factory `Set.of` từ chối phần tử trùng, còn `Set.copyOf` nhận một collection và tạo tập không trùng. Nếu trùng lặp trong dữ liệu đầu vào là lỗi nghiệp vụ, phải **kiểm tra trùng trước khi copy**, không coi `Set.copyOf` là bộ phát hiện lỗi trùng.

Với những object khác nhau nhưng có `equals` bằng nhau, quy tắc API cho phép chọn một đại diện bất kỳ trong nhóm bằng nhau. Không viết mã dựa trên việc nhất định giữ “phần tử đầu tiên” khi các object có thông tin phụ khác nhau. Đối với mã định danh bất biến chuẩn hóa thành chuỗi, đây thường không phải vấn đề.

## 3. So sánh `Set.copyOf` với các cách tạo tập khác

| Cách tạo | Có thể sửa qua kết quả? | Có phản ánh thay đổi sau đó ở nguồn? | Tình huống thích hợp |
| --- | --- | --- | --- |
| `new HashSet<>(source)` | **Có** | Không, đối với cấu trúc tập mới | Tập làm việc mutable |
| `Set.copyOf(source)` | **Không** | Không, đối với cấu trúc/thay phần tử của nguồn | Xuất bản tập giá trị ổn định |
| `Set.of("A", "B")` | **Không** | Không có collection nguồn cần sao chép | Tập hằng nhỏ viết trực tiếp |
| `Collections.unmodifiableSet(source)` | **Không qua wrapper** | **Có** nếu backing set đổi | Read-only **view** có chủ đích |
| `EnumSet.of(Permission.READ, Permission.WRITE)` | **Có** | Không có nguồn ngoài | Tập enum mutable, hiệu quả cho xử lý |
| `Set.copyOf(enumSet)` | **Không** | Không, đối với sửa đổi của `enumSet` | Xuất bản snapshot quyền enum |

Với bộ mã cấu hình được tạo từ tập hợp đầu vào thay đổi, `Set.copyOf` thường làm rõ ý định hơn `Collections.unmodifiableSet(source)`. Wrapper chỉ **ngăn người nhận gọi mutator thông qua wrapper** nhưng vẫn có thể nhìn thấy thay đổi từ tham chiếu nguồn còn tồn tại.

~~~java
var backing = new HashSet<>(Set.of("READ"));
var view = Collections.unmodifiableSet(backing);
var snapshot = Set.copyOf(backing);

backing.add("WRITE");
// view.contains("WRITE") == true
// snapshot.contains("WRITE") == false
~~~

Đoạn trên là ví dụ minh họa nằm trong một phương thức/lớp có import phù hợp. Thêm `"WRITE"` thông qua `backing` làm `view` đổi theo. Còn `snapshot` là tập đã xuất bản ở thời điểm trước.

**Không nên dùng wrapper với mục tiêu “đóng băng cấu hình”** nếu các thành phần khác vẫn giữ tham chiếu mutable tới nguồn. Nếu thật sự cần một view cập nhật theo nguồn, hãy gọi đúng nó là “view” và quy định rõ quyền cập nhật, đồng bộ và vòng đời của dữ liệu.

## 4. Dùng `Set.copyOf` cho danh mục giá trị hợp lệ

### 4.1. Đầu vào có thể đến từ nơi nào?

Một danh mục mã hợp lệ có thể được đọc từ tệp cấu hình, database, response API hoặc dữ liệu khởi tạo. Trước khi chuyển thành tập cho mã khác sử dụng, nên tách các công đoạn:

1. Nhận dữ liệu đầu vào.
2. Kiểm tra `null`, giá trị rỗng và quy tắc định dạng.
3. Chuẩn hóa mã nếu nghiệp vụ quy định không phân biệt chữ hoa/chữ thường, khoảng trắng đầu/cuối.
4. Quyết định xử lý các mã lặp.
5. Xuất bản bằng `Set.copyOf`.
6. Sử dụng `contains` để kiểm tra tư cách thành viên.

Ví dụ, với mã danh mục ASCII được thiết kế không phân biệt hoa/thường:

~~~java
static Set<String> publishCatalog(Collection<String> raw) {
    Objects.requireNonNull(raw, "catalog source");
    var normalized = new ArrayList<String>();
    for (var code : raw) {
        var canonical = Objects.requireNonNull(code, "catalog code")
                .strip().toUpperCase(Locale.ROOT);
        if (canonical.isEmpty()) {
            throw new IllegalArgumentException("blank catalog code");
        }
        normalized.add(canonical);
    }
    return Set.copyOf(normalized);
}
~~~

Đây là một **phương thức để đặt trong một lớp**; cần import `Collection`, `Set`, `Objects`, `ArrayList` và `Locale`. Chương trình đầy đủ ở mục 7 có thể biên dịch/chạy trực tiếp.

Hàm này chọn hợp đồng cụ thể:

- Không cho phép collection nguồn `null`.
- Không cho phép mã `null`.
- Không cho phép mã chỉ gồm khoảng trắng.
- Chuẩn hóa mã bằng `strip()` và `toUpperCase(Locale.ROOT)` để việc so sánh mã ổn định, không phụ thuộc locale máy chạy.
- Cho phép các mã trùng sau chuẩn hóa và gom chúng thành một phần tử vì danh mục có ý nghĩa **tập hợp**, không phải danh sách các bản ghi có thứ tự.
- Trả một tập không thể sửa.

Chính sách **chuẩn hóa** và **xử lý trùng** phải đến từ nghiệp vụ. Với mã phân biệt chữ hoa/chữ thường, không được tự chuyển toàn bộ mã thành chữ hoa. Với dữ liệu mà trùng lặp là lỗi cấu hình, cần phát hiện trùng thay vì lặng lẽ gom bằng set.

### 4.2. Kiểm tra giá trị có trong danh mục

~~~java
var catalog = publishCatalog(List.of(" BASIC ", "PLUS", "basic"));
// catalog có hai giá trị BASIC và PLUS.

boolean basicAllowed = catalog.contains("BASIC"); // true
boolean adminAllowed = catalog.contains("ADMIN"); // false
~~~

Nếu chuỗi người dùng đưa vào chưa được chuẩn hóa thì phải dùng **cùng một quy tắc chuẩn hóa** ở điểm kiểm tra. Ví dụ, khi nghiệp vụ xác định mã là ASCII không phân biệt hoa/thường:

~~~java
var requested = " basic ";
var normalizedRequest = requested.strip().toUpperCase(Locale.ROOT);
var accepted = catalog.contains(normalizedRequest);
~~~

Cần kiểm tra `requested != null` hoặc xử lý null theo hợp đồng trước khi gọi `strip()`. Đừng nhầm việc một tập **không chứa null** với việc phương thức `contains(null)` trên mọi triển khai đều phải trả `false`; một số unmodifiable set từ các factory có thể ném `NullPointerException` khi kiểm tra null. Hãy xác thực đầu vào trước.

### 4.3. Đừng dùng thứ tự duyệt của set làm thứ tự hiển thị

~~~java
var catalog = Set.copyOf(List.of("PLUS", "BASIC"));
// Không dựa vào System.out.println(catalog) để có thứ tự cố định.
var sortedForDisplay = new TreeSet<>(catalog);
System.out.println(sortedForDisplay); // [BASIC, PLUS]
~~~

`TreeSet` dùng thứ tự tự nhiên của chuỗi ở ví dụ này. Trong một giao diện thực tế có thứ tự ưu tiên nghiệp vụ, hãy lưu **danh sách thứ tự hiển thị riêng** hoặc sort bằng comparator của nghiệp vụ. Bản chất của `Set` là kiểm tra tính duy nhất/tư cách thành viên, **không phải quản lý thứ tự các hạng mục**.

### 4.4. Danh mục rỗng có hợp lệ không?

~~~java
var emptyCatalog = Set.<String>of();      // Set<String> rỗng
var emptyCopy = Set.copyOf(List.<String>of()); // Set<String> rỗng
~~~

Cả hai hợp lệ về Java. Nhưng “danh mục rỗng” có được phép trong ứng dụng hay không phụ thuộc nghiệp vụ. Ví dụ, tập tính năng bật có thể rỗng; danh mục loại sản phẩm bắt buộc có ít nhất một mã thì nên kiểm tra `isEmpty()` và từ chối cấu hình nếu rỗng.

## 5. Dùng `Set.copyOf` cho tập quyền hạn

### 5.1. Quyền là một tập giá trị, không phải danh sách có thứ tự

Với các quyền được khai báo dưới dạng enum:

~~~java
enum Permission {
    VIEW_REPORT,
    EDIT_REPORT,
    APPROVE_REPORT
}
~~~

Một tập quyền phù hợp để kiểm tra:

~~~java
var mutableGrants = EnumSet.of(
        Permission.VIEW_REPORT,
        Permission.EDIT_REPORT);

Set<Permission> grantedSnapshot = Set.copyOf(mutableGrants);
boolean canEdit = grantedSnapshot.contains(Permission.EDIT_REPORT);
~~~

Lợi ích:

- `EnumSet` là một tập enum **có thể sửa** để xây dựng tập quyền trong logic nội bộ.
- `Set.copyOf` tạo kết quả **không thể sửa** từ tập quyền đã chốt.
- Kiểu `Permission` giúp tránh nhập nhằng với các chuỗi tự do như `"edit"`, `"EDIT"`.
- `contains` nêu ý nghĩa kiểm tra quyền và không phụ thuộc thứ tự phần tử.
- Mã nhận `Set<Permission>` không có quyền sửa tập snapshot qua API của nó.

Nhưng **không nên hiểu** rằng chỉ riêng `Set.copyOf` là một hệ thống phân quyền an toàn. Tập quyền phải được lấy từ nguồn tin cậy ở phía server và được kiểm tra tại điểm thực thi hành động. Bất kỳ tập quyền do client tự gửi lên đều phải được xác minh, không được tin tưởng chỉ vì nó đã được copy thành unmodifiable.

### 5.2. Lưu ý quan trọng về thu hồi quyền

Nếu tập nguồn thay đổi sau khi tạo snapshot, snapshot **không tự thay đổi**:

~~~java
var currentGrants = EnumSet.of(
        Permission.VIEW_REPORT,
        Permission.EDIT_REPORT);

Set<Permission> snapshot = Set.copyOf(currentGrants);
currentGrants.remove(Permission.EDIT_REPORT);

// snapshot.contains(Permission.EDIT_REPORT) vẫn là true.
var freshSnapshot = Set.copyOf(currentGrants);
// freshSnapshot.contains(Permission.EDIT_REPORT) là false.
~~~

Đây không phải lỗi của `Set.copyOf` — đây là **đặc điểm snapshot**, rất hữu ích cho tính nhất quán của dữ liệu. Tuy nhiên, với bảo mật, snapshot cũ có thể trở nên **lạc hậu** khi quyền bị thu hồi.

Thiết kế phân quyền phải xác định rõ:

- **Thời điểm** lấy quyền: đầu request, khi tạo session, khi kiểm tra mỗi thao tác hay theo chu kỳ.
- **Nguồn sự thật**: database quyền, dịch vụ IAM, policy engine hoặc cấu hình server đáng tin cậy.
- **Khi nào cần làm mới/invalidate** snapshot: đổi vai trò, thu hồi quyền, cập nhật policy.
- **Độ trễ thu hồi quyền chấp nhận được** theo độ nhạy của hành động.
- Có cần **kiểm tra lại quyền tại điểm thực thi** thay vì dựa vào tập quyền đã gắn trên giao diện từ trước hay không.

Đối với thao tác nhạy cảm, không dùng một snapshot sống vô thời hạn nếu nghiệp vụ yêu cầu thu hồi quyền có hiệu lực ngay. Muốn cập nhật tập quyền, hãy **tạo một snapshot mới rồi thay tham chiếu được công bố**, hoặc đánh giá lại quyền từ nguồn tin cậy, thay vì cố gọi `add/remove` trên snapshot cũ.

### 5.3. Bản sao không thay cho việc kiểm tra nguồn cấp quyền

Một ứng dụng có thể hiển thị nút “Duyệt” chỉ khi `permissions.contains(APPROVE_REPORT)`. Tuy nhiên, backend vẫn cần kiểm tra quyền khi nhận request duyệt. Ẩn một nút trên giao diện không phải biện pháp thực thi phân quyền.

Ví dụ mã minh họa bên server:

~~~java
static void approveReport(Set<Permission> currentPermissions) {
    if (!currentPermissions.contains(Permission.APPROVE_REPORT)) {
        throw new SecurityException("Approval permission required");
    }
    // Thực hiện xử lý sau khi kiểm tra policy thích hợp.
}
~~~

Đây là một phương thức minh họa cần đặt trong lớp chứa `Permission`, không phải tệp Java độc lập. Tham số `currentPermissions` chỉ nên được cung cấp bởi **bộ phận xác thực/phân quyền tin cậy**, không lấy trực tiếp từ body request hoặc tham số của client.

### 5.4. `EnumSet.copyOf` và `Set.copyOf` không giống nhau

~~~java
var working = EnumSet.of(Permission.VIEW_REPORT);
var anotherWorking = EnumSet.copyOf(working); // EnumSet mutable
var published = Set.copyOf(working);         // Unmodifiable Set
~~~

`EnumSet.copyOf` phù hợp nếu cần bản sao **mutable** của tập enum để thao tác nội bộ. `Set.copyOf` phù hợp để **xuất bản bản sao unmodifiable**.

Cần lưu ý: `EnumSet.copyOf(Collection)` có các quy tắc riêng về việc suy ra enum type khi collection rỗng; với tập rỗng mới, có thể chủ động dùng `EnumSet.noneOf(Permission.class)`. `Set.copyOf` chấp nhận collection rỗng và trả set rỗng không thể sửa.

## 6. Ranh giới null, trùng lặp và kiểu phần tử

### 6.1. `null` phải được xử lý trước khi tạo snapshot

~~~java
var raw = Arrays.asList("BASIC", null);
// Set.copyOf(raw); // NullPointerException
~~~

`Set.copyOf(null)` cũng ném `NullPointerException` vì collection nguồn là null.

Với quyền enum, một phần tử `null` thường là dữ liệu không hợp lệ và cần bị từ chối. Không nên tự âm thầm loại null khi điều đó có thể che giấu lỗi ánh xạ quyền:

~~~java
static Set<Permission> publishGrants(Collection<Permission> trusted) {
    Objects.requireNonNull(trusted, "trusted grants");
    return Set.copyOf(trusted); // Từ chối null permission.
}
~~~

Đây là phương thức minh họa với `Permission` là enum. Nó **không xác minh tính hợp lệ của nguồn cấp quyền**: nếu nguồn không đáng tin, cần kiểm tra xác thực/policy ở một tầng khác.

### 6.2. Trùng lặp trong catalog và tập quyền

~~~java
var repeatedCodes = List.of("BASIC", "BASIC", "PLUS");
var catalog = Set.copyOf(repeatedCodes);
System.out.println(catalog.size()); // 2
~~~

Nếu trùng mã là bình thường, việc gom thành set là hợp lý. Nếu trùng trong cấu hình nghĩa là dữ liệu hỏng, hãy phát hiện trùng *trước* khi tạo set, hoặc đối chiếu kích thước sau khi copy với số phần tử đầu vào (với dữ liệu đã được chuẩn hóa và không chứa null). Mọi kiểm tra này cần được viết theo **quy tắc bằng nhau** của kiểu phần tử.

### 6.3. Đừng dùng phần tử mutable làm khóa/tư cách thành viên nếu có thể tránh

`HashSet` và nhiều kiểu set phụ thuộc `equals`/`hashCode` của phần tử. Nếu một phần tử mutable thay đổi dữ liệu dùng để tính hash sau khi đã nằm trong tập, những lần gọi `contains` có thể cho kết quả không mong muốn. `Set.copyOf` không biến phần tử mutable thành immutable.

Với danh mục, ưu tiên **String mã đã chuẩn hóa**, enum hoặc value object bất biến đúng nghĩa. Với tập quyền, **enum** thường phù hợp: giá trị có danh tính ổn định, không có dữ liệu mutable trong chính mỗi hằng quyền.

~~~java
// Dữ liệu danh mục bất biến đơn giản:
record FeatureCode(String value) {
    FeatureCode {
        Objects.requireNonNull(value, "value");
    }
}
~~~

Ví dụ record trên chỉ bất biến nông; ở đây `String` là immutable nên thành phần `value` ổn định. Không biến record thành “bảo đảm bất biến sâu” nếu record có thành phần là `List` mutable hoặc object mutable khác.

## 7. Chương trình Java 17+ hoàn chỉnh

Ví dụ dưới đây kiểm tra trực tiếp hai ứng dụng của `Set.copyOf`:

- Danh mục mã: chuẩn hóa, gộp bản ghi trùng, sắp xếp riêng để hiển thị, không thay đổi sau khi dữ liệu nguồn được thêm phần tử.
- Tập quyền: snapshot ban đầu, thu hồi quyền trong tập nguồn, kiểm tra snapshot cũ và snapshot mới, ngăn sửa qua API.
- So sánh với `Collections.unmodifiableSet`: một view có thể phản ánh thay đổi của backing collection.

~~~java
// File: SetCopyOfCatalogPermissionsDemo.java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class SetCopyOfCatalogPermissionsDemo {
    enum Permission { VIEW_REPORT, EDIT_REPORT, APPROVE_REPORT }

    static Set<String> publishCatalog(Collection<String> raw) {
        Objects.requireNonNull(raw, "catalog source");
        var normalized = new ArrayList<String>();
        for (var code : raw) {
            var canonical = Objects.requireNonNull(code, "catalog code")
                    .strip().toUpperCase(Locale.ROOT);
            if (canonical.isEmpty()) {
                throw new IllegalArgumentException("blank catalog code");
            }
            normalized.add(canonical);
        }
        return Set.copyOf(normalized);
    }

    public static void main(String[] args) {
        var incoming = new ArrayList<>(List.of(" basic ", "PLUS", "basic"));
        var catalog = publishCatalog(incoming);
        System.out.println("catalog sorted = " + new TreeSet<>(catalog));
        System.out.println("catalog contains BASIC = " + catalog.contains("BASIC"));
        incoming.add("ADMIN");
        System.out.println("catalog excludes ADMIN after source change = "
                + !catalog.contains("ADMIN"));

        System.out.println("duplicates collapsed = "
                + Set.copyOf(List.of("A", "A", "B")).size());
        try {
            Set.copyOf(Arrays.asList("A", null));
            System.out.println("null rejected = false");
        } catch (NullPointerException expected) {
            System.out.println("null rejected = true");
        }

        var currentGrants = EnumSet.of(Permission.VIEW_REPORT, Permission.EDIT_REPORT);
        Set<Permission> grantedSnapshot = Set.copyOf(currentGrants);
        System.out.println("snapshot EDIT initially = "
                + grantedSnapshot.contains(Permission.EDIT_REPORT));
        currentGrants.remove(Permission.EDIT_REPORT);
        System.out.println("snapshot EDIT after source revocation = "
                + grantedSnapshot.contains(Permission.EDIT_REPORT));
        var updatedSnapshot = Set.copyOf(currentGrants);
        System.out.println("new snapshot EDIT = "
                + updatedSnapshot.contains(Permission.EDIT_REPORT));

        try {
            grantedSnapshot.remove(Permission.EDIT_REPORT);
            System.out.println("snapshot mutation blocked = false");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot mutation blocked = true");
        }

        var backing = new HashSet<>(Set.of("READ"));
        var readOnlyView = Collections.unmodifiableSet(backing);
        backing.add("WRITE");
        System.out.println("read-only view reflects WRITE = "
                + readOnlyView.contains("WRITE"));
    }
}
~~~

Lưu tệp dưới tên `SetCopyOfCatalogPermissionsDemo.java`, sau đó biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac --release 17 SetCopyOfCatalogPermissionsDemo.java
java SetCopyOfCatalogPermissionsDemo
~~~

Kết quả stdout đã kiểm thử:

~~~text
catalog sorted = [BASIC, PLUS]
catalog contains BASIC = true
catalog excludes ADMIN after source change = true
duplicates collapsed = 2
null rejected = true
snapshot EDIT initially = true
snapshot EDIT after source revocation = true
new snapshot EDIT = false
snapshot mutation blocked = true
read-only view reflects WRITE = true
~~~

Giải thích theo thứ tự:

1. `publishCatalog` chuẩn hóa `" basic "` và `"basic"` thành `"BASIC"`, nên danh mục có hai mã duy nhất. `TreeSet` chỉ được dùng để in ra thứ tự ổn định `[BASIC, PLUS]`.
2. `catalog.contains("BASIC")` trả true. Sau khi `incoming.add("ADMIN")`, snapshot vẫn không chứa ADMIN.
3. `Set.copyOf(List.of("A","A","B"))` có hai phần tử, không phát sinh lỗi trùng như `Set.of("A","A","B")`.
4. `Arrays.asList("A", null)` tạo danh sách có phần tử null để thử chính sách của **`Set.copyOf`**; ngoại lệ `NullPointerException` được bắt có chủ đích.
5. `grantedSnapshot` có quyền EDIT ở thời điểm xuất bản. Khi gọi `currentGrants.remove(EDIT_REPORT)`, snapshot cũ **vẫn** có quyền ấy. `updatedSnapshot` được tạo từ nguồn sau thu hồi thì không chứa EDIT.
6. `grantedSnapshot.remove(EDIT_REPORT)` bị chặn bằng `UnsupportedOperationException`. Việc có tham chiếu đến một `Set<Permission>` không đồng nghĩa người nhận được sửa quyền hiệu lực đã xuất bản.
7. `Collections.unmodifiableSet(backing)` là view: khi `backing` thêm `"WRITE"`, view thấy giá trị này. Đó là khác biệt quan trọng với `Set.copyOf`.

Chương trình cố ý chỉ in kích thước, kết quả `contains` và danh sách **đã sắp xếp**. Nó không dựa vào thứ tự duyệt ngẫu nhiên của một unmodifiable set.

## 8. Thiết kế cập nhật và công bố tập quyền

### 8.1. Không cập nhật một snapshot bằng cách mutate

Cách tư duy không phù hợp:

~~~java
Set<Permission> currentPermissions = Set.copyOf(source);
// currentPermissions.add(Permission.APPROVE_REPORT); // Không được hỗ trợ.
~~~

Khi cần thay đổi quyền, tạo một tập làm việc rồi xuất bản snapshot mới:

~~~java
var mutable = EnumSet.of(Permission.VIEW_REPORT);
mutable.add(Permission.EDIT_REPORT);
Set<Permission> published = Set.copyOf(mutable);

// Khi policy có thay đổi:
mutable.remove(Permission.EDIT_REPORT);
Set<Permission> newer = Set.copyOf(mutable);
~~~

Tham chiếu `published` vẫn giữ tập cũ; `newer` là tập mới. Nếu nhiều thành phần đọc tập quyền trong một service, cần có cơ chế **công bố tham chiếu mới** phù hợp với mô hình đồng thời và quy tắc hiệu lực của quyền.

### 8.2. Công bố snapshot an toàn giữa các luồng

Một cách tổng quát để công bố một tập đã được xây dựng là giữ tham chiếu trong `AtomicReference<Set<Permission>>`:

~~~java
// Mã minh họa khi Permission đã được khai báo.
var current = new java.util.concurrent.atomic.AtomicReference<Set<Permission>>(
        Set.of(Permission.VIEW_REPORT));

// Khi tính được tập quyền từ nguồn tin cậy:
var nextPermissions = Set.copyOf(
        EnumSet.of(Permission.VIEW_REPORT, Permission.EDIT_REPORT));
current.set(nextPermissions);

// Tại nơi đọc:
var snapshot = current.get();
var mayEdit = snapshot.contains(Permission.EDIT_REPORT);
~~~

Thao tác `set/get` công bố/tham chiếu snapshot qua một biến tham chiếu an toàn với đồng thời; không cần mutate collection sau khi xuất bản. Tuy nhiên, **điều này không tự giải quyết tính mới của dữ liệu, xác thực người dùng, quyền của từng đối tượng hay bảo đảm thu hồi quyền ngay lập tức**. Việc tính lại policy, xác minh nguồn và kiểm soát thời điểm cập nhật vẫn là trách nhiệm riêng của hệ thống.

### 8.3. Đừng coi trạng thái quyền lưu lâu là nguồn chân lý

Với quyền có thể thu hồi trong runtime, một snapshot có thể hợp lệ **tại thời điểm T1** nhưng không còn hợp lệ **tại T2**. Nếu hệ thống kiểm tra quyền theo snapshot T1 ở T2 mà không có cơ chế làm mới, nguy cơ là **cấp quyền dựa trên dữ liệu cũ**. Hãy gắn snapshot với vòng đời phù hợp: request, session có cơ chế invalidation, phiên bản policy, hoặc kiểm tra trực tiếp từ nguồn xác thực theo yêu cầu bảo mật.

Đối với ứng dụng web, việc ẩn/hiện nút dựa trên tập quyền trên client chỉ là **trải nghiệm giao diện**, không phải enforcement. Server cần kiểm tra ủy quyền trước khi thực hiện thao tác nhạy cảm, bằng dữ liệu và policy hiện hành phù hợp.

## 9. Giá trị rỗng, thứ tự, phân biệt catalog với workflow

### 9.1. Tập rỗng

Tập rỗng có thể biểu thị “không có quyền” hoặc “không có giá trị nào được bật”:

~~~java
Set<Permission> none = Set.of();
var noCodes = Set.<String>of();
~~~

`Set.copyOf` trên collection rỗng cũng hợp lệ. Việc hợp lệ về Java không có nghĩa ứng dụng nên cho phép cấu hình không có bất kỳ danh mục nào; cần kiểm tra theo nghiệp vụ. Đối với phân quyền, mặc định không có quyền có thể hợp lý, nhưng phải dựa vào chính sách an toàn đã được xác định.

### 9.2. Không dùng set để quản lý mức ưu tiên

Giả sử danh mục có thứ tự hiển thị **BASIC → PLUS → PRO**. `Set.copyOf` phù hợp để kiểm tra mã có hợp lệ hay không nhưng không duy trì thứ tự hiển thị đó. Nếu cần thứ tự, nên lưu thêm `List<String>` theo thứ tự mong muốn hoặc sắp xếp với comparator rõ ràng.

Tương tự, nếu quy trình duyệt quyền phải thực hiện theo thứ tự, tập quyền không phải một workflow engine. `Set.copyOf` chỉ thể hiện **tư cách thành viên trong một tập giá trị**, không thể hiện trình tự thao tác hay ràng buộc “đã được phê duyệt bởi ai”.

### 9.3. Khi thay đổi catalog

Nếu cấu hình catalog thay đổi, phải tạo tập mới:

~~~java
var oldCodes = Set.copyOf(List.of("BASIC", "PLUS"));
var newCodes = Set.copyOf(List.of("BASIC", "PLUS", "PRO"));

// oldCodes vẫn không có PRO.
~~~

Cần xác định các thành phần tiêu thụ **đọc snapshot nào**, và tại thời điểm nào giá trị mới có hiệu lực. Với cấu hình được cập nhật nóng, cần quy trình thay tham chiếu hoặc làm mới theo vòng đời thay vì giả định bản sao cũ tự được cập nhật.

## 10. Bảo đảm và giới hạn: không nhầm unmodifiable với immutable toàn hệ thống

### 10.1. Unmodifiable không phải deep immutable

~~~java
var mutableName = new StringBuilder("A");
var snapshot = Set.copyOf(List.of(mutableName));
mutableName.append("B");
// Phần tử được giữ vẫn là cùng object StringBuilder đã thay đổi.
~~~

Đây là ví dụ cho thấy phần tử mutable có thể đổi trạng thái, **không phải một khuyến nghị đặt `StringBuilder` vào set**. Nếu trạng thái phần tử tham gia `equals`/`hashCode`, thay đổi nó sau khi đưa vào set còn có thể làm các phép `contains`/tra cứu hoạt động không như kỳ vọng.

Khi làm danh mục và tập quyền, hãy ưu tiên các phần tử bất biến như `String` đã chuẩn hóa, enum hoặc value object bất biến được thiết kế đúng cách.

### 10.2. `Set.copyOf` không tự xử lý race khi nguồn đang thay đổi

Lấy bản sao từ một collection đang bị luồng khác sửa đồng thời **không tự tạo giao dịch atomic**. Tùy collection/đường duyệt, có thể gặp kết quả không mong muốn hoặc ngoại lệ. Cần điều phối đọc/ghi nguồn, sử dụng snapshot ổn định hoặc cấu trúc dữ liệu thread-safe phù hợp.

Việc kết quả unmodifiable giúp giảm nhiều lỗi do sửa cấu trúc sau khi công bố, nhưng không thay thế cơ chế đồng bộ, không làm các phần tử mutable thread-safe và không thay thế authorization policy.

### 10.3. Không dựa vào danh tính của tập kết quả

Nếu nguồn đã là một unmodifiable set phù hợp, `Set.copyOf` có thể trả chính nguồn. Các unmodifiable sets từ factory có đặc tính *value-based*: không nên dùng `==` để kiểm tra xem một snapshot mới có được cấp phát hay không, cũng không nên khóa đồng bộ trên đối tượng set đó.

Kiểm thử bằng **giá trị và hành vi**:

~~~java
var a = Set.copyOf(List.of("BASIC", "PLUS"));
var b = Set.of("PLUS", "BASIC");

System.out.println(a.equals(b)); // true; Set equality không phụ thuộc thứ tự
~~~

Những kiểm thử quan trọng khác: không nhận null, không cho sửa, không phản ánh sửa đổi collection nguồn, và xử lý đúng khi policy/catalog được cập nhật.

## 11. Những lỗi thường gặp

| Ngộ nhận | Sự thật và cách khắc phục |
| --- | --- |
| “`Set.copyOf` chỉ bọc một view nên nguồn đổi thì copy đổi theo.” | Không. Kết quả không phản ánh các thao tác sửa nguồn sau khi copy; wrapper `Collections.unmodifiableSet` mới là read-only view. |
| “`Set.copyOf` và `Set.of` xử lý đầu vào trùng giống nhau.” | `Set.copyOf` gom phần tử bằng nhau; `Set.of` từ chối đối số trùng. |
| “`Set.copyOf` tự bỏ phần tử `null`.” | Sai. Phần tử `null` làm phát sinh `NullPointerException`. |
| “Danh mục tạo từ `Set.copyOf` giữ thứ tự file cấu hình.” | Không được bảo đảm. Dùng danh sách thứ tự hoặc comparator khi hiển thị. |
| “Tập quyền không thể sửa là tập quyền luôn mới.” | Sai. Snapshot có thể cũ nếu quyền nguồn đã bị thu hồi. |
| “Dùng `var` làm phần tử thành `Object` hoặc làm set mutable.” | Sai. `var` chỉ suy luận kiểu tĩnh từ initializer, không thay đổi hợp đồng `Set.copyOf`. |
| “`EnumSet.copyOf` và `Set.copyOf` đều unmodifiable.” | Sai. `EnumSet.copyOf` tạo bản sao enum set mutable, `Set.copyOf` trả unmodifiable set. |
| “Unmodifiable set bảo đảm object phần tử không đổi.” | Sai. Không có deep copy mặc định. |
| “Có thể tin quyền do client gửi vì đã biến thành `Set.copyOf`.” | Sai. Không thể dùng copy thay xác minh nguồn quyền hay kiểm tra ở server. |
| “Khi quyền bị thu hồi, bản sao cũ cũng mất quyền đó.” | Sai. Phải làm mới/đổi snapshot hoặc đánh giá lại từ nguồn tin cậy. |
| “Tập đã copy chắc chắn có object identity mới.” | Không được giả định; API có thể tái sử dụng nguồn phù hợp. |
| “Set thích hợp để biểu diễn thứ tự duyệt danh mục.” | Sai nếu cần thứ tự xác định; set dùng cho tính duy nhất và kiểm tra thành viên. |

## 12. Bài tập tự kiểm tra và đáp án

### Câu 1 — Sau khi thay đổi nguồn

~~~java
var source = new HashSet<>(Set.of("A", "B"));
var published = Set.copyOf(source);
source.add("C");
~~~

**Hỏi:** `published.contains("C")` bằng gì?

**Đáp án:** `false`. `Set.copyOf` là snapshot về các phần tử, không phải view của `source`.

### Câu 2 — Danh sách trùng

~~~java
var codes = Set.copyOf(List.of("BASIC", "BASIC", "PRO"));
~~~

**Hỏi:** `codes.size()` bằng mấy, có lỗi không?

**Đáp án:** `2`; không có lỗi trùng. Tuy nhiên, nếu trùng mã là lỗi nghiệp vụ, phải phát hiện nó bằng validation riêng.

### Câu 3 — Chính sách null

~~~java
var source = Arrays.asList("READ", null);
var permissions = Set.copyOf(source);
~~~

**Hỏi:** Kết quả gì?

**Đáp án:** Ném `NullPointerException`, không tạo tập có phần tử null và không tự loại phần tử null.

### Câu 4 — Quyền bị thu hồi

~~~java
var mutable = EnumSet.of(Permission.VIEW_REPORT, Permission.EDIT_REPORT);
var old = Set.copyOf(mutable);
mutable.remove(Permission.EDIT_REPORT);
var fresh = Set.copyOf(mutable);
~~~

**Hỏi:** Kiểm tra `EDIT_REPORT` ở `old` và `fresh` khác nhau thế nào?

**Đáp án:** `old.contains(EDIT_REPORT)` vẫn `true`; `fresh.contains(EDIT_REPORT)` là `false`. Hệ thống phân quyền phải xác định thời điểm làm mới snapshot; không được dùng quyền cũ khi policy yêu cầu thu hồi ngay.

### Câu 5 — View so với snapshot

~~~java
var backing = new HashSet<>(Set.of("A"));
var view = Collections.unmodifiableSet(backing);
var copied = Set.copyOf(backing);
backing.add("B");
~~~

**Đáp án:** `view.contains("B")` là `true`, còn `copied.contains("B")` là `false`.

### Câu 6 — Tập nào mutable?

~~~java
var enumWorking = EnumSet.of(Permission.VIEW_REPORT);
var enumCopy = EnumSet.copyOf(enumWorking);
var published = Set.copyOf(enumWorking);
~~~

**Đáp án:** `enumWorking` và `enumCopy` mutable; `published` unmodifiable. `EnumSet.copyOf` hữu ích cho bản sao làm việc; `Set.copyOf` hữu ích khi xuất bản quyền.

### Câu 7 — Thứ tự hiển thị

Nguồn đầu vào là `["PRO", "BASIC", "PLUS"]`. Có nên mong `Set.copyOf` in ra đúng thứ tự này không?

**Đáp án:** Không. Nếu UI cần thứ tự cố định, lưu thứ tự riêng hoặc sắp xếp bằng comparator. Set không cam kết thứ tự duyệt.

### Câu 8 — Quyền từ client

Một request gửi `["APPROVE_REPORT"]` và service gọi `Set.copyOf(requestPermissions)` trước khi phê duyệt. Điều này đã đủ an toàn chưa?

**Đáp án:** Chưa. `Set.copyOf` chỉ tạo tập không thể sửa, **không xác thực người dùng hay chứng minh quyền được cấp**. Server phải đánh giá quyền từ nguồn chính sách tin cậy của người dùng đã được xác thực.

### Câu 9 — Bất biến sâu

Một `Set.copyOf` chứa phần tử mutable mà `hashCode` có thể thay đổi. Có nên sửa phần tử sau khi tạo set không?

**Đáp án:** Không. Việc đổi trường tham gia `equals`/`hashCode` có thể làm phép `contains`/tra cứu không đáng tin cậy. Dùng phần tử bất biến cho danh mục và quyền hạn.

## 13. Checklist khi đưa `Set.copyOf` vào sản phẩm

- **Nguồn dữ liệu:** Quyền/danh mục lấy từ đâu; nguồn có đáng tin và đã được xác thực chưa?
- **Validation:** Đã kiểm tra `null`, mã rỗng, format, case, khoảng trắng và mã trùng theo hợp đồng chưa?
- **Cấu trúc:** Nghiệp vụ có thực sự là tập giá trị duy nhất không, hay cần thứ tự và số lần lặp?
- **Phần tử:** Có dùng String/enum/value object bất biến để tránh lỗi hash và thay đổi ngầm không?
- **Xuất bản:** Có chủ đích chọn snapshot `Set.copyOf` thay vì read-only view `Collections.unmodifiableSet` không?
- **Cập nhật:** Khi catalog/role đổi, thành phần nào tạo và thay thế snapshot?
- **Thu hồi quyền:** Snapshot cũ sống bao lâu, có cơ chế invalidation hoặc kiểm tra lại ở điểm thực thi không?
- **Đồng thời:** Việc lấy snapshot từ nguồn mutable và công bố cho các luồng đọc có được phối hợp an toàn không?
- **Bảo mật:** Mã kiểm tra authorization ở server đã dùng nguồn policy tin cậy chưa?
- **Kiểm thử:** Có kiểm tra trùng, null, unmodifiable, source mutation, thứ tự hiển thị và stale permissions chưa?

## 14. Tài liệu chuẩn hiện hành

- [Java SE API — `Set.copyOf` và Unmodifiable Sets](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html): đặc tính không thể sửa, null, trùng lặp, thứ tự và dữ liệu nguồn.
- [Java SE API — `Set.of`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html#of()): factory set unmodifiable, quy tắc đối số trùng.
- [Java SE API — `Collections.unmodifiableSet`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set)): wrapper read-only view và backing set.
- [Java SE API — `EnumSet`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumSet.html): tập enum mutable và các factory/copy phù hợp.
- [Java SE API — `AtomicReference`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): cơ chế công bố/thay tham chiếu phù hợp với đồng thời.
- [JEP 269 — Convenience Factory Methods for Collections](https://openjdk.org/jeps/269): nền tảng các factory unmodifiable hiện đại được tiếp tục hỗ trợ.
- [Java Language Specification — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): quy tắc của `var` khi dùng trong ví dụ.

**Ghi nhớ:** `Set.copyOf` rất phù hợp để **chốt một snapshot không thể sửa** của các mã danh mục hoặc quyền hạn. Kiểm tra dữ liệu trước khi copy; không dựa vào thứ tự duyệt hoặc object identity; ưu tiên phần tử bất biến. Với **quyền truy cập**, snapshot chỉ đúng cho một thời điểm: phải có quy trình làm mới khi policy đổi và thực thi kiểm tra ở phía server từ nguồn tin cậy.