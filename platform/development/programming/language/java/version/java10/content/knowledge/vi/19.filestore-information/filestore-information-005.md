# UnsupportedOperationException khi nhà cung cấp FileStore không hỗ trợ (Java 10+)

## 1. Bài toán và mục tiêu

`java.nio.file.FileStore` là abstraction của Java NIO.2 đại diện cho một vùng lưu trữ: ổ đĩa, phân vùng, volume, storage pool, hệ thống tệp gắn kết hoặc một loại storage do nhà cung cấp (*file system provider*) triển khai. Ứng dụng có thể dùng nó để đọc thông tin dung lượng, loại vùng lưu trữ, khả năng chỉ đọc và một số thuộc tính riêng của hệ thống tệp.

Từ **Java 10**, `FileStore` có thêm `getBlockSize()` để hỏi **số byte trong một block** của vùng lưu trữ. Tuy nhiên, một `FileStore` hợp lệ **không bắt buộc** phải hỗ trợ truy vấn này. Nếu provider không triển khai chức năng, lời gọi có thể ném:

```text
java.lang.UnsupportedOperationException
```

Đây không nhất thiết là một lỗi Java hay tình huống hỏng ổ đĩa: nó có thể đơn giản nghĩa là **khả năng đang hỏi không có trong provider này**. Hợp đồng Java SE hiện hành cho phép hành vi đó.

Bài học tập trung vào:

1. Vì sao `FileStore.getBlockSize()` có thể ném `UnsupportedOperationException`, kể cả trên JDK mới.
2. Những trường hợp tương tự khi đọc thuộc tính tùy chọn qua `FileStore.getAttribute(String)`.
3. Cách phân biệt **không hỗ trợ tính năng** với **I/O thất bại**, **không tồn tại thuộc tính** hoặc **view không khả dụng**.
4. Dùng đúng `supportsFileAttributeView(...)` và `getFileStoreAttributeView(...)`, không nhầm chúng với khả năng hỗ trợ `getBlockSize()`.
5. Thiết kế API có kết quả “không biết/không hỗ trợ” thay vì đoán số block size hoặc che giấu lỗi.
6. Viết ví dụ Java 10+ **chạy nhất quán trên mọi hệ điều hành** bằng FileStore mô phỏng, rồi áp dụng thật với `Files.getFileStore(path)`.
7. Kiểm thử các nhánh success, unsupported và I/O error; xử lý khả năng khác nhau giữa local disk, network filesystem, in-memory filesystem và provider tùy biến.

Mọi kiến thức trong bài dựa trên API **vẫn còn áp dụng trong Java hiện đại**. Không cần API đã lỗi thời hoặc cách làm legacy.

## 2. FileStore liên hệ với FileSystemProvider như thế nào?

Một `Path` thuộc về một `FileSystem`, và một `FileSystem` có provider điều phối hành vi I/O. FileStore tương ứng với vùng lưu trữ chứa đường dẫn đó:

```java
import java.nio.file.Files;
import java.nio.file.FileStore;
import java.nio.file.Path;
import java.nio.file.Paths;

Path location = Paths.get(".").toAbsolutePath().normalize();
FileStore store = Files.getFileStore(location);
```

Đây là đoạn để đặt trong một phương thức có xử lý `IOException`; không phải file Java độc lập.

Có nhiều loại implementation hợp lệ:

- Provider của hệ thống tệp mặc định trên các môi trường khác nhau.
- Volume cục bộ, ổ đĩa mạng hoặc vùng lưu trữ được mount qua hệ điều hành.
- Filesystem do thư viện hoặc ứng dụng triển khai, chẳng hạn filesystem trong bộ nhớ.
- Provider chỉ cung cấp một phần metadata mà hệ điều hành hoặc hệ thống phía dưới cho phép truy vấn.

Do vậy **cùng một chương trình** có thể nhận thông tin block size trên môi trường A, nhưng gặp `UnsupportedOperationException` trên môi trường B. Không viết code dựa vào giả định “đã chạy được ở máy của tôi thì mọi FileStore đều có block size”.

`Files.getFileStore(path)` cũng có thể thất bại vì I/O, permission hoặc tình trạng storage. Việc **lấy được một object FileStore** không đồng nghĩa mọi metadata tùy chọn đều có thể đọc.

### Những phương thức cơ bản cần nhận diện

| Phương thức | Ý nghĩa | Điểm cần nhớ |
| --- | --- | --- |
| `name()` | Tên vùng lưu trữ | Nội dung phụ thuộc implementation |
| `type()` | Loại vùng lưu trữ | Không coi chuỗi này là feature flag chính thức |
| `isReadOnly()` | Khả năng chỉ đọc | Không đoán block size từ đó |
| `getTotalSpace()` | Tổng dung lượng, đơn vị byte | Có thể ném `IOException` |
| `getUsableSpace()` | Số byte có thể sử dụng theo góc nhìn JVM | Chỉ là số liệu gợi ý tại một thời điểm |
| `getUnallocatedSpace()` | Số byte chưa phân bổ | Cũng là số liệu gợi ý, có thể nhanh chóng thay đổi |
| `getBlockSize()` | Số byte mỗi block | **Có thể ném `UnsupportedOperationException`** |
| `supportsFileAttributeView(...)` | Có hỗ trợ một loại **file attribute view** không? | Không phải phép thử `getBlockSize` |
| `getFileStoreAttributeView(Class)` | Lấy view thuộc tính **của FileStore** | Trả `null` nếu view không có |
| `getAttribute(String)` | Đọc một thuộc tính FileStore theo tên | Có thể ném `UnsupportedOperationException` |

Cần đọc Javadoc của **từng phương thức**, không áp dụng một quy tắc ngoại lệ cho cả class.

## 3. Cơ chế đặc biệt của getBlockSize() từ Java 10

Chữ ký:

```java
public long getBlockSize() throws java.io.IOException
```

Hợp đồng:

- Nếu được hỗ trợ và đọc thành công, trả một giá trị **dương** biểu diễn số **byte mỗi block** của FileStore.
- Nếu I/O gặp lỗi, có thể ném `IOException`.
- Nếu thao tác không được hỗ trợ, ném `UnsupportedOperationException`.
- Phương thức được đưa vào **Java 10**. Đây vẫn là API hợp lệ trong Java SE hiện hành.

Chi tiết rất quan trọng trong Javadoc chính thức:

> The implementation in this class throws UnsupportedOperationException.

Có nghĩa là **implementation mặc định tại chính lớp FileStore** ném `UnsupportedOperationException`. Một subclass/provider muốn cung cấp block size phải override phương thức theo hợp đồng phù hợp. Vì đây là một phương thức concrete có implementation mặc định, một provider không override vẫn có thể là một implementation FileStore hợp lệ, nhưng **không thể hỏi block size bằng phương thức đó**.

Đây là lý do không nên suy luận rằng:

- “JDK đã nâng cấp lên phiên bản mới thì provider tự hỗ trợ.”
- “`getTotalSpace()` chạy được, nên `getBlockSize()` chắc chắn chạy.”
- “`supportsFileAttributeView("basic")` trả true, nên mọi thông tin FileStore đều có.”
- “FileStore trên Linux/Windows/macOS luôn phải trả `4096`.”
- “Nếu `getBlockSize()` thất bại thì filesystem đã hỏng.”

Thay vào đó, coi block size là **metadata tùy chọn**. Việc không có metadata đó phải được diễn đạt như “unsupported/unknown”, không ghi một con số thiếu cơ sở.

## 4. UnsupportedOperationException không giống IOException

Hai tình huống này khác nhau về **ý nghĩa**, cách thử lại và cách báo cáo:

### UnsupportedOperationException

```java
try {
    long blockSize = store.getBlockSize();
    System.out.println(blockSize);
} catch (UnsupportedOperationException ex) {
    System.out.println("Block size is not supported by this FileStore");
}
```

Đoạn này giả định `store` đã được khai báo và phương thức chứa nó xử lý `IOException`.

- `UnsupportedOperationException` là **unchecked exception** thuộc nhánh `RuntimeException`.
- Nó báo **operation không được hỗ trợ**, không tự động chứng minh có sự cố vật lý của storage.
- Gọi lại liên tục trên cùng provider và cùng cấu hình **thường không tự làm tính năng xuất hiện**. Chỉ retry khi có lý do rõ ràng về thay đổi provider/môi trường hoặc theo chiến lược đã xác định.

### IOException

```java
try {
    long blockSize = store.getBlockSize();
    System.out.println(blockSize);
} catch (UnsupportedOperationException ex) {
    System.out.println("Unsupported capability");
} catch (java.io.IOException ex) {
    System.err.println("I/O failed while reading block size: " + ex.getMessage());
}
```

- `IOException` là **checked exception**.
- Nó nói có lỗi ở quá trình truy vấn I/O, chứ không nói tính năng chắc chắn không tồn tại.
- Nếu dữ liệu cần thiết để thực hiện nghiệp vụ, thường phải **báo lỗi lên caller** hoặc để boundary quản lý retry theo chính sách. Không âm thầm trả số giả.

**Không nên bắt chung `Exception`, ghi log rồi dùng `4096` hoặc `0` cho mọi trường hợp.** Làm vậy mất phân loại “không hỗ trợ” và “đang lỗi”, khiến monitoring và quyết định phân bổ dữ liệu sai.

Một bảng phân loại:

| Tình huống | Java signal | Nên xử lý |
| --- | --- | --- |
| Provider có block size | Trả `long > 0` | Dùng dữ liệu như metadata hiện tại |
| Provider không có chức năng | `UnsupportedOperationException` | Ghi nhận `UNKNOWN/UNSUPPORTED` hoặc bỏ tính năng tùy chọn |
| I/O thất bại | `IOException` | Báo lỗi hoặc retry có chính sách |
| Lấy FileStore từ Path lỗi | `Files.getFileStore` có thể ném `IOException` | Chẩn đoán đường dẫn/FS/permission |
| Tên attribute không hỗ trợ | `getAttribute` có thể ném `UnsupportedOperationException` | Không đoán giá trị attribute |
| FileStoreAttributeView không khả dụng | `getFileStoreAttributeView` trả `null` | Kiểm tra null trước khi sử dụng |

## 5. Đọc metadata tùy chọn bằng OptionalLong

Một cách thiết kế hợp đồng có chủ đích cho thông tin có thể vắng mặt là `OptionalLong`:

```java
import java.io.IOException;
import java.nio.file.FileStore;
import java.util.OptionalLong;

static OptionalLong readBlockSize(FileStore fileStore) throws IOException {
    try {
        return OptionalLong.of(fileStore.getBlockSize());
    } catch (UnsupportedOperationException unsupported) {
        return OptionalLong.empty();
    }
}
```

Đây là một phương thức có thể đặt trong class Java; bản chạy đầy đủ ở mục 11.

Ưu điểm:

1. Giá trị dương được trả khi provider hỗ trợ.
2. Trường hợp **không hỗ trợ** trở thành `OptionalLong.empty()`.
3. `IOException` **được giữ nguyên và chuyển lên caller**, không bị ngụy trang thành “không hỗ trợ”.
4. Không cần dùng `0`, `-1` hoặc số block size giả định làm sentinel.
5. Caller quyết định liệu metadata này có bắt buộc đối với chức năng của họ hay không.

Ví dụ sử dụng:

```java
OptionalLong blockSize = readBlockSize(store);

if (blockSize.isPresent()) {
    System.out.println("Block size: " + blockSize.getAsLong() + " bytes");
} else {
    System.out.println("Block size: unknown (provider unsupported)");
}
```

Đoạn này giả định `store` và phương thức `readBlockSize` có sẵn; code đặt trong một phương thức có khai báo/bao bắt `IOException`.

**Quan trọng về ý nghĩa:** `OptionalLong.empty()` ở ví dụ này được định nghĩa là “không hỗ trợ”, vì wrapper chỉ bắt ngoại lệ đó. Nếu ứng dụng muốn phân biệt nhiều trạng thái như “chưa thử”, “bị từ chối do permission”, “không hỗ trợ”, “I/O failure”, nên thiết kế một result type có enum trạng thái và cause rõ ràng, thay vì đẩy mọi trường hợp vào `OptionalLong.empty()`.

## 6. Phân biệt khả năng hỗ trợ FileAttributeView và block size

`FileStore` có hai overload:

```java
boolean supportsFileAttributeView(
        Class<? extends java.nio.file.attribute.FileAttributeView> type);

boolean supportsFileAttributeView(String name);
```

Chúng hỏi về **file attribute view**, chẳng hạn `BasicFileAttributeView` hoặc tên `"basic"`, không phải khả năng của mọi phương thức `FileStore`.

Theo đặc tả, phép kiểm tra đối với `BasicFileAttributeView` hoặc tên `"basic"` trả `true`. Nhưng **điều đó không bảo đảm `getBlockSize()` được hỗ trợ**.

```java
boolean basicAvailable =
        store.supportsFileAttributeView(
                java.nio.file.attribute.BasicFileAttributeView.class);

// Không suy luận:
// if (basicAvailable) store.getBlockSize(); // Chưa được bảo đảm.
```

Trên một số filesystem không cục bộ, Javadoc còn lưu ý khả năng phát hiện file attribute view của default provider có thể có giới hạn về độ chính xác. Vì vậy, kiểm tra view chỉ thích hợp cho **chức năng của view đó**, không phải một lời hứa thay thế cho `try/catch` khi gọi metadata tùy chọn.

**Không có một phương thức `FileStore.supportsGetBlockSize()` chuẩn.** Khi ứng dụng cần thử khả năng này, hãy gọi `getBlockSize()` ở một ranh giới được kiểm soát và xử lý riêng `UnsupportedOperationException`.

## 7. FileStoreAttributeView và getAttribute(String) là hai cơ chế khác

Ngoài file attribute view dành cho tệp, FileStore còn có **store attribute view**:

```java
<V extends java.nio.file.attribute.FileStoreAttributeView> V
        getFileStoreAttributeView(Class<V> type)
```

Theo Javadoc, nó trả **một object view** nếu khả dụng, hoặc **`null`** khi view yêu cầu không tồn tại.

Vì vậy:

```java
// Giả định VendorStoreView là kiểu FileStoreAttributeView của provider.
VendorStoreView view = store.getFileStoreAttributeView(
        VendorStoreView.class);

if (view == null) {
    // Không có view này; không dereference.
}
```

Đoạn code này là **minh họa** với một interface `VendorStoreView` riêng, không có sẵn trong Java SE. Ở mục 11 có định nghĩa interface mô phỏng để chạy.

Cơ chế khác là:

```java
Object value = store.getAttribute("view-name:attribute-name");
```

Tên thuộc tính có dạng `view-name:attribute-name`. Với view không khả dụng hoặc thuộc tính không thể đọc, `getAttribute` có thể ném **`UnsupportedOperationException`**; với lỗi I/O, có thể ném **`IOException`**. Kết quả đọc attribute cũng có thể là `null` nếu **attribute thực sự có giá trị null** theo hợp đồng provider.

Ví dụ của Javadoc là một attribute dành cho ZFS nếu view tương ứng có hỗ trợ:

```java
// Chỉ minh họa cho provider thực sự hỗ trợ attribute:
// boolean compression = (Boolean) store.getAttribute("zfs:compression");
```

Không copy dòng này vào một ứng dụng đa nền tảng rồi giả định mọi FileStore đều hiểu `"zfs:compression"`. Những attribute riêng phải được đặt dưới hợp đồng provider/OS; và cần kiểm tra kiểu trả về trước khi cast khi giá trị đến từ provider không được kiểm soát.

**Đừng đánh đồng ba cách diễn đạt không hỗ trợ:**

| Cơ chế | Phương thức | Khi không khả dụng |
| --- | --- | --- |
| Block size | `getBlockSize()` | `UnsupportedOperationException` |
| Store attribute đọc theo tên | `getAttribute("view:attr")` | `UnsupportedOperationException` |
| Store attribute view kiểu mạnh | `getFileStoreAttributeView(View.class)` | `null` |
| File attribute view capability | `supportsFileAttributeView(...)` | `false` nếu view không được hỗ trợ; riêng basic được bảo đảm true |

`getFileStoreAttributeView` và `supportsFileAttributeView` nói về **hai loại view khác nhau**. Không dùng cái này làm phép kiểm tra tổng quát cho cái kia.

## 8. Không dùng unsupported block size để đoán allocation hoặc quota

Một số chương trình tính toán nhầm:

```java
long block = store.getBlockSize();
long estimatedAllocated = (fileSize + block - 1) / block * block;
```

Đây **không phải** một công thức phân bổ dung lượng được Java SE bảo đảm cho mọi filesystem. Ngoài nguy cơ `getBlockSize()` không được hỗ trợ, cách tính này còn có thể sai vì:

- **Sparse files** có lỗ trống không chiếm block vật lý tương ứng với kích thước logic.
- Compression, deduplication, copy-on-write, metadata và các cơ chế phân bổ riêng.
- Kích thước dữ liệu vật lý có thể khác logical file size và đơn vị block báo cáo.
- Filesystem có nhiều tầng lưu trữ hay quy tắc phân bổ phức tạp.
- Công thức cộng `fileSize + block - 1` còn có thể **overflow long** khi số rất lớn.

Block size chỉ là **một loại metadata của FileStore**, không phải hợp đồng dự đoán chính xác số byte sử dụng bởi một tệp.

Tương tự, `getUsableSpace()` và `getUnallocatedSpace()` trả về các **số liệu gợi ý tại thời điểm truy vấn**, không đảm bảo rằng một phép ghi tương lai sẽ thành công. Dung lượng có thể đổi do tiến trình khác, quota, permission hoặc lỗi I/O. Đừng ép các API đó thành “đảm bảo ghi được N byte”.

Nếu mục tiêu là kiểm tra quota hay khả năng tạo tệp, cần thiết kế kiểm tra cụ thể và **vẫn xử lý lỗi của thao tác ghi thực tế**.

## 9. Truy cập FileStore thực tế: code theo hợp đồng, không đoán môi trường

Ví dụ đọc block size của vùng lưu trữ chứa thư mục làm việc:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.FileStore;
import java.nio.file.Paths;

var path = Paths.get(".").toAbsolutePath().normalize();

try {
    FileStore store = Files.getFileStore(path);
    try {
        long bytes = store.getBlockSize();
        System.out.println("Block size: " + bytes + " bytes");
    } catch (UnsupportedOperationException unsupported) {
        System.out.println("Block size: unsupported by this provider");
    }
} catch (IOException ioFailure) {
    System.err.println("Cannot query storage: " + ioFailure.getMessage());
}
```

Đoạn này minh họa các câu lệnh trong một phương thức; không phải một file chạy độc lập.

**Không công bố stdout cố định** cho ví dụ chạy trên FileStore thật: tên, loại và block size phụ thuộc filesystem/provider/OS. Với một volume thực tế, `getBlockSize()` có thể trả một số dương; với provider khác, có thể ném `UnsupportedOperationException`.

Ở ứng dụng phân quyền hạn chế, thao tác cũng có thể bị từ chối theo cơ chế security của môi trường. Không đánh đồng vấn đề quyền với việc một metadata không được provider triển khai.

Nếu muốn in thêm:

```java
System.out.println("name=" + store.name());
System.out.println("type=" + store.type());
System.out.println("readOnly=" + store.isReadOnly());
```

Những thông tin này phục vụ chẩn đoán nhưng **không được dùng làm feature detector chính thức của getBlockSize()**. Code review nên yêu cầu xử lý ngoại lệ dựa vào chính hợp đồng của lời gọi cần dùng.

## 10. Thiết kế hành vi fallback có trách nhiệm

Cần tách hai nhóm nhu cầu.

### Nhóm A — block size chỉ để hiển thị/quan sát

Ứng dụng quản lý storage hiển thị các thông tin như:

```text
Capacity: 1 TB
Usable: 250 GB
Block size: UNKNOWN
```

Khi không hỗ trợ, việc hiển thị `UNKNOWN` hoặc `Unsupported` là phù hợp. **Không hiển thị `0 B`**, vì `getBlockSize()` được hỗ trợ phải trả số dương và `0` dễ bị hiểu như một dữ kiện thực.

Có thể thiết kế:

```java
static java.util.OptionalLong optionalBlockSize(FileStore store)
        throws java.io.IOException {
    try {
        return java.util.OptionalLong.of(store.getBlockSize());
    } catch (UnsupportedOperationException ignored) {
        return java.util.OptionalLong.empty();
    }
}
```

Nếu truy vấn I/O thất bại, ngoại lệ tiếp tục nổi lên để dashboard phân loại là **ERROR** thay vì hiển thị `UNKNOWN`.

### Nhóm B — block size là điều kiện bắt buộc của thuật toán

Nếu một operation **thực sự cần block size chính xác**, việc nhận `UnsupportedOperationException` nên dẫn đến **từ chối operation hoặc chuyển sang thuật toán khác có hợp đồng phù hợp**. Không im lặng dùng `4096` như một hằng số phổ quát.

Ví dụ chính sách:

```java
static long requiredBlockSize(FileStore store)
        throws java.io.IOException {
    try {
        return store.getBlockSize();
    } catch (UnsupportedOperationException ex) {
        throw new IllegalStateException(
                "This operation requires block-size metadata", ex);
    }
}
```

Đoạn này đổi ngoại lệ thành lỗi nghiệp vụ được mô tả, đồng thời **giữ cause ban đầu**. Chỉ nên làm khi thật sự có một precondition không thể bỏ qua.

**Lưu ý:** Nếu thuật toán có thể hoạt động đúng mà không biết block size, tốt hơn nên thiết kế đường fallback độc lập với metadata này, thay vì tạo một exception không cần thiết.

## 11. Chương trình Java 10+ hoàn chỉnh: kiểm chứng có/không hỗ trợ và I/O lỗi

Không nên viết bài test phụ thuộc vào việc máy CI có FileStore nào ném `UnsupportedOperationException`. Một số máy trả block size, máy khác không; test kiểu đó sẽ không ổn định.

Thay vào đó, tạo một **FileStore mô phỏng có chủ đích**:

- `SyntheticStore` chỉ triển khai các thành viên abstract; **không override** `getBlockSize()`, nên kế thừa implementation mặc định ném `UnsupportedOperationException`.
- `SupportedStore` override để trả block size dương.
- `FailingStore` override để ném `IOException` nhằm kiểm tra nhánh lỗi.
- `getAttribute` mô phỏng một attribute hợp lệ và một attribute không được hỗ trợ.
- `getFileStoreAttributeView` trả `null` theo hợp đồng khi view không khả dụng.

Tạo file **`FileStoreUnsupportedDemo.java`**:

```java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.attribute.BasicFileAttributeView;
import java.nio.file.attribute.FileAttributeView;
import java.nio.file.attribute.FileStoreAttributeView;
import java.util.OptionalLong;

public final class FileStoreUnsupportedDemo {
    interface VendorStoreView extends FileStoreAttributeView { }

    static class SyntheticStore extends FileStore {
        @Override public String name() { return "synthetic"; }
        @Override public String type() { return "test"; }
        @Override public boolean isReadOnly() { return false; }
        @Override public long getTotalSpace() { return 1_000_000L; }
        @Override public long getUsableSpace() { return 700_000L; }
        @Override public long getUnallocatedSpace() { return 800_000L; }

        @Override
        public boolean supportsFileAttributeView(
                Class<? extends FileAttributeView> type) {
            return type == BasicFileAttributeView.class;
        }

        @Override
        public boolean supportsFileAttributeView(String name) {
            return "basic".equals(name);
        }

        @Override
        public <V extends FileStoreAttributeView> V getFileStoreAttributeView(
                Class<V> type) {
            return null;
        }

        @Override
        public Object getAttribute(String attribute) throws IOException {
            if ("demo:mode".equals(attribute)) {
                return "test-only";
            }
            throw new UnsupportedOperationException("Unknown store attribute");
        }

        // Không override getBlockSize(): thừa hưởng mặc định của FileStore.
    }

    static final class SupportedStore extends SyntheticStore {
        @Override public long getBlockSize() { return 4096L; }
    }

    static final class FailingStore extends SyntheticStore {
        @Override public long getBlockSize() throws IOException {
            throw new IOException("simulated I/O error");
        }
    }

    static OptionalLong readBlockSize(FileStore fileStore) throws IOException {
        try {
            return OptionalLong.of(fileStore.getBlockSize());
        } catch (UnsupportedOperationException unsupported) {
            return OptionalLong.empty();
        }
    }

    static String describeBlockSize(FileStore fileStore) throws IOException {
        OptionalLong value = readBlockSize(fileStore);
        return value.isPresent() ? value.getAsLong() + " bytes" : "UNKNOWN";
    }

    public static void main(String[] args) throws Exception {
        var legacyProvider = new SyntheticStore();
        System.out.println("basicView=" +
                legacyProvider.supportsFileAttributeView(BasicFileAttributeView.class));
        System.out.println("unsupportedBlockSize=" +
                describeBlockSize(legacyProvider));
        System.out.println("totalSpace=" + legacyProvider.getTotalSpace());
        System.out.println("supportedCustomAttribute=" +
                legacyProvider.getAttribute("demo:mode"));

        try {
            legacyProvider.getAttribute("vendor:compression");
        } catch (UnsupportedOperationException expected) {
            System.out.println("unsupportedAttribute=UnsupportedOperationException");
        }

        System.out.println("missingStoreView=" +
                (legacyProvider.getFileStoreAttributeView(VendorStoreView.class) == null));
        System.out.println("supportedBlockSize=" +
                describeBlockSize(new SupportedStore()));

        try {
            describeBlockSize(new FailingStore());
        } catch (IOException expected) {
            System.out.println("blockIoError=" + expected.getMessage());
        }
    }
}
```

Chạy với JDK có hỗ trợ biên dịch Java 10:

```bash
javac --release 10 FileStoreUnsupportedDemo.java
java FileStoreUnsupportedDemo
```

**Stdout chính xác đã được biên dịch và chạy kiểm chứng:**

```text
basicView=true
unsupportedBlockSize=UNKNOWN
totalSpace=1000000
supportedCustomAttribute=test-only
unsupportedAttribute=UnsupportedOperationException
missingStoreView=true
supportedBlockSize=4096 bytes
blockIoError=simulated I/O error
```

### Phân tích từng phần đầu ra

1. `basicView=true` minh họa FileStore có thể hỗ trợ `BasicFileAttributeView`. Điều này **không ngụ ý** nó hỗ trợ block size.
2. `unsupportedBlockSize=UNKNOWN` là nhánh `SyntheticStore` không override `getBlockSize()`; hành vi ném `UnsupportedOperationException` đến từ **implementation mặc định của FileStore**.
3. `totalSpace=1000000` cho thấy một provider có thể trả số liệu dung lượng nhưng vẫn **không hỗ trợ** block size.
4. `supportedCustomAttribute=test-only` là một thuộc tính `demo:mode` do provider **mô phỏng** định nghĩa, không phải attribute chung của Java SE.
5. `unsupportedAttribute=UnsupportedOperationException` minh họa `getAttribute` có thể từ chối tên view/attribute mà provider không hỗ trợ.
6. `missingStoreView=true` thể hiện API dạng `getFileStoreAttributeView` trả `null` khi view không có, **khác** nhánh exception của `getAttribute`.
7. `supportedBlockSize=4096 bytes` là trường hợp subclass override và trả dữ liệu. **4096 chỉ là giá trị fixture**, không phải giá trị bắt buộc của mọi filesystem.
8. `blockIoError=simulated I/O error` chứng minh wrapper không nuốt `IOException`. Nếu provider hỗ trợ truy vấn nhưng thực thi thất bại, caller vẫn nhìn thấy lỗi đó.

**Tại sao demo mô phỏng lại đáng tin?** Vì nó kiểm tra nhánh được định nghĩa trong API mà **không phụ thuộc vào máy chạy test**. Một bài test tích hợp bổ sung trên filesystem thật nên kiểm tra rằng code xử lý đúng một trong hai tình huống block size hợp lệ hoặc UnsupportedOperationException, thay vì assert cứng một con số.

Tất cả API trong chương trình đã có từ Java 10 hoặc trước đó và vẫn tồn tại trên JDK hiện đại.

## 12. Kiểm thử provider thực: đừng khẳng định kết quả cụ thể

Trong test tích hợp hoặc công cụ chẩn đoán, có thể lấy FileStore từ một `Path` thực:

```java
var store = java.nio.file.Files.getFileStore(
        java.nio.file.Paths.get(".").toAbsolutePath().normalize());

try {
    long size = store.getBlockSize();
    if (size <= 0) {
        throw new AssertionError("Provider returned non-positive block size");
    }
    System.out.println("Block size=" + size);
} catch (UnsupportedOperationException unsupported) {
    System.out.println("Block size not supported here");
}
```

Đoạn này đặt trong một phương thức xử lý `IOException`. Nó có output **phụ thuộc môi trường**, nên bài này **không** tuyên bố stdout của phần này là cố định.

Thực hành kiểm thử đúng:

- Nhánh **supported**: chỉ kiểm tra block size dương, không assert luôn bằng `4096` hay `512`.
- Nhánh **unsupported**: xác nhận ứng dụng báo `UNKNOWN` và không thực hiện tính toán phụ thuộc block size.
- Nhánh **I/O failure**: nên mô phỏng để xác minh code không nuốt lỗi; khó và không cần tạo hỏng hóc storage thật.
- Provider đa nền tảng: chạy trên các loại filesystem quan trọng của sản phẩm nếu có thể; không coi test trên một máy là bằng chứng mọi provider giống nhau.

Nếu cần kiểm tra attribute riêng của hệ thống tệp, chỉ chạy ca đó trên provider đã công bố hỗ trợ; các hệ thống tệp không có attribute là **tình huống không hỗ trợ bình thường** trong phạm vi API tùy chọn.

## 13. Hỗ trợ tính năng không phải thông tin vĩnh viễn của toàn bộ hệ thống

Không được gắn một cờ toàn cục kiểu `BLOCK_SIZE_SUPPORTED=true` chỉ vì truy vấn trên một FileStore thành công. Cùng ứng dụng có thể làm việc với:

- Nhiều ổ đĩa hoặc mount point.
- Nhiều provider khác nhau trong cùng một JVM.
- Tệp nằm trên hệ thống mạng hoặc filesystem ảo.
- Cấu hình runtime thay đổi sau khi mount/unmount hoặc khi chuyển môi trường.

Khả năng đọc metadata là **đặc tính của FileStore/provider và bối cảnh truy vấn**, không phải tất cả `Path` trong ứng dụng đều giống nhau.

Nếu cache, cần chọn scope theo đối tượng FileStore/đường dẫn hoặc danh tính lưu trữ phù hợp, có chiến lược refresh nếu môi trường có thay đổi. Không dùng `name()`/`type()` như một khóa cache tuyệt đối trên mọi provider vì định dạng và tính duy nhất của các chuỗi này không được Java SE bảo đảm phổ quát.

Đối với một dashboard quan sát nhiều volume, việc volume A không có block size không nên làm toàn bộ bảng điều khiển thất bại khi metadata đó chỉ mang tính bổ sung. Nhưng nếu một thao tác nghiệp vụ **cần** block size, phải dừng chức năng phụ thuộc một cách rõ ràng.

## 14. Đừng che giấu lỗi bằng catch quá rộng

Anti-pattern:

```java
try {
    return store.getBlockSize();
} catch (Exception ex) {
    return 4096;
}
```

Đây là đoạn minh họa đặt trong một phương thức có kiểu trả về `long` và biến `store` được khai báo.

Vấn đề:

1. `Exception` bắt cả `IOException` và `UnsupportedOperationException`, khiến hai nguyên nhân bị gộp thành một.
2. Giá trị `4096` chỉ là **giả định**; không bảo đảm đúng.
3. Log/metrics không còn phân biệt provider thiếu chức năng với storage đang lỗi.
4. Phép tính dùng block size giả có thể đưa ra quyết định sai, nhất là về performance, allocation hoặc quota.
5. Nếu tiến trình cần fail-fast, default ngầm khiến lỗi đi xa hơn mới phát hiện.

Cách tốt hơn:

```java
static java.util.OptionalLong blockSizeIfAvailable(
        java.nio.file.FileStore store) throws java.io.IOException {
    try {
        return java.util.OptionalLong.of(store.getBlockSize());
    } catch (UnsupportedOperationException unsupported) {
        return java.util.OptionalLong.empty();
    }
}
```

Và tại nơi gọi:

```java
var blockSize = blockSizeIfAvailable(store);

if (blockSize.isPresent()) {
    // Sử dụng giá trị được provider trả.
} else {
    // Bỏ qua tùy chọn hoặc báo unknown; không đoán.
}
```

**Lưu ý về ranh giới catch:** Đặt `try/catch` bao quanh **đúng lời gọi có khả năng ném UnsupportedOperationException**. Không bao trùm một đoạn xử lý nghiệp vụ dài, vì `UnsupportedOperationException` phát sinh từ một chỗ khác có thể báo lỗi lập trình thật sự, không phải “metadata chưa có”.

## 15. Metrics, logging và phản ứng của API

Trong hệ thống quan sát storage, các trạng thái nên được ghi rõ:

| Trạng thái đo block size | Ý nghĩa | Gợi ý hiển thị |
| --- | --- | --- |
| `AVAILABLE` | Đọc được block size dương | “4096 B” hoặc giá trị được trả thật |
| `UNSUPPORTED` | Provider không hỗ trợ operation | “N/A — unsupported” |
| `ERROR` | I/O thất bại khi truy vấn | “Query failed” cùng nguyên nhân được log |
| `NOT_QUERIED` | Chưa có yêu cầu truy vấn | “Not measured” |

Không dùng `0` cho cả ba trạng thái chưa có dữ liệu, vì số 0 trông như một phép đo hợp lệ. Có thể dùng `OptionalLong` cho supported/unsupported và kênh exception riêng cho error. Nếu cần đủ bốn trạng thái, định nghĩa một kiểu kết quả có enum và trường dữ liệu thích hợp.

Nguyên tắc logging:

- Không spam log ở mỗi vòng refresh khi provider luôn unsupported; đây có thể là đặc điểm bình thường của hệ thống.
- Ghi exception I/O với bối cảnh đủ dùng để chẩn đoán, không xuất thông tin nhạy cảm tùy tiện.
- Nếu hệ thống yêu cầu tuân thủ SLA về metadata, phát tín hiệu tương ứng với tính năng quan trọng; không đánh đồng unsupported với hỏng volume.
- Không xây dựng vòng retry dày đặc cho một operation không hỗ trợ.

## 16. Lỗi thường gặp trong bài và trong code review

**Lỗi 1 — Cho rằng `getBlockSize()` tồn tại từ Java 10 thì mọi provider phải hỗ trợ.** Sai. Implementation mặc định của `FileStore` ném `UnsupportedOperationException`; provider có thể không override.

**Lỗi 2 — Bắt `IOException` nhưng quên `UnsupportedOperationException`.** Sai. `UnsupportedOperationException` là unchecked; khai báo `throws IOException` không tự bắt loại này.

**Lỗi 3 — Bắt mọi exception rồi trả `4096`.** Sai. Đó là số giả định, không phải hợp đồng của mọi filesystem.

**Lỗi 4 — Dùng `supportsFileAttributeView("basic")` làm phép kiểm tra block size.** Sai. Đây là capability của file attribute view, không phải của `getBlockSize`.

**Lỗi 5 — Gọi `getFileStoreAttributeView(...)` rồi không kiểm tra null.** Sai. API cho phép trả null khi view không có; không nên truy cập method trên null.

**Lỗi 6 — Gọi `getAttribute("zfs:compression")` trên mọi volume.** Sai. Attribute và view đó là phụ thuộc provider, không phải tính năng chung của Java.

**Lỗi 7 — Coi `getAttribute` trả null và ném UnsupportedOperationException là một nghĩa.** Không hẳn: null có thể là **giá trị hợp lệ** của attribute; exception biểu thị view/attribute không hỗ trợ đọc.

**Lỗi 8 — Tưởng block size là số byte mà một tệp nhất định chiếm trên đĩa.** Sai. Sparse files, compression và filesystem metadata có thể làm khác biệt lớn.

**Lỗi 9 — Cho rằng `getUsableSpace()` bảo đảm có thể ghi từng ấy byte.** Sai. Đây là thông tin gợi ý có thể thay đổi ngay sau khi đọc.

**Lỗi 10 — Kiểm thử block size theo con số trên máy phát triển.** Sai. Integration tests phải chấp nhận cả nhánh unsupported, còn unit tests dùng mô phỏng.

**Lỗi 11 — Dùng `store.name()` hoặc `store.type()` để suy ra provider có hỗ trợ chức năng.** Sai. Các chuỗi phụ thuộc implementation và không tạo một API phát hiện block size chính thức.

**Lỗi 12 — Dùng một `catch (UnsupportedOperationException)` rộng quanh cả luồng xử lý.** Sai. Ngoại lệ của bước nghiệp vụ khác có thể bị nuốt, che giấu lỗi lập trình.

**Lỗi 13 — Coi unsupported là lỗi quyền truy cập.** Không mặc định vậy. Unsupported báo thao tác không được cung cấp; permission/I/O phải được phân loại riêng theo hợp đồng từng API.

**Lỗi 14 — Đóng hoặc hủy một FileStore như resource.** `FileStore` là object mô tả lưu trữ, không phải stream cần `close()`. Tài nguyên cụ thể như `FileChannel`/`InputStream` phải được quản lý theo hợp đồng riêng.

## 17. Checklist trước khi triển khai

- [ ] Đã xác định **metadata nào là tùy chọn** và metadata nào là bắt buộc.
- [ ] `getBlockSize` được gọi trong `try` đủ hẹp, có `catch UnsupportedOperationException` riêng.
- [ ] `IOException` không bị ép thành “unsupported”; caller/handler có chính sách rõ ràng.
- [ ] Kết quả unsupported được biểu diễn bằng `OptionalLong.empty()` hoặc trạng thái explicit, không phải số block size giả.
- [ ] Không dựa vào `supportsFileAttributeView` để suy ra khả năng đọc block size.
- [ ] Kiểm tra `null` khi dùng `getFileStoreAttributeView`.
- [ ] Kiểm tra hợp đồng riêng khi dùng `getAttribute("view:attribute")`.
- [ ] Không lấy attribute provider-specific làm điều kiện chạy chung trên mọi filesystem.
- [ ] Không suy ra actual disk allocation, quota hay guarantee ghi từ block size.
- [ ] Có test success, UOE và IOException trong một mock/synthetic provider ổn định.
- [ ] Có integration test đa nền tảng khi ứng dụng triển khai nhiều loại FileStore.
- [ ] Observability phân biệt supported, unsupported và error, tránh retry/log spam không cần thiết.
- [ ] Không chỉnh behavior dựa vào chuỗi `name/type` không được chuẩn hóa.
- [ ] Các test không assert cứng `4096` trên provider thực.

## 18. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Trên Java 10+, `FileStore.getBlockSize()` có luôn trả số dương không?

**Đáp án:** Không. Khi được hỗ trợ và thành công, nó trả số dương theo byte; nếu không hỗ trợ thì `UnsupportedOperationException`, còn lỗi I/O có thể gây `IOException`.

**Câu 2.** Vì sao một subclass FileStore không override getBlockSize vẫn có thể hợp lệ?

**Đáp án:** `getBlockSize()` có implementation mặc định trong `FileStore` và implementation ấy ném `UnsupportedOperationException`. Provider không nhất thiết triển khai metadata tùy chọn này.

**Câu 3.** `supportsFileAttributeView("basic") == true` có bảo đảm đọc được block size không?

**Đáp án:** Không. Basic view thuộc file attributes; nó không chứng minh `getBlockSize()` được provider hỗ trợ.

**Câu 4.** Làm sao phân biệt không hỗ trợ và I/O failure?

**Đáp án:** Bắt `UnsupportedOperationException` tại lời gọi tương ứng để biểu diễn unavailable, và bắt/lan truyền `IOException` theo chính sách lỗi. Không gộp chúng bằng `catch Exception` rồi trả số cố định.

**Câu 5.** Vì sao không dùng `0` làm block size khi không hỗ trợ?

**Đáp án:** Hợp đồng thành công trả số dương; dùng 0 dễ tạo thông tin đo sai, dẫn đến phép tính sai hoặc hiểu nhầm. Dùng “unknown/unsupported” hoặc OptionalLong.

**Câu 6.** Khi `getFileStoreAttributeView(MyView.class)` trả `null`, điều đó nghĩa gì?

**Đáp án:** View đó không có sẵn theo hợp đồng phương thức. Không dereference; chọn tính năng khác hoặc báo unavailable.

**Câu 7.** `getAttribute("vendor:feature")` có thể ném loại ngoại lệ nào khi view hoặc attribute không khả dụng?

**Đáp án:** `UnsupportedOperationException`. Lỗi I/O là `IOException`; một số attribute có thể trả giá trị null hợp lệ.

**Câu 8.** Khi FileStore trả `4096` block size, có thể kết luận mọi tệp nhỏ hơn 4096 byte chiếm đúng 4096 byte vật lý không?

**Đáp án:** Không. Cách phân bổ phụ thuộc filesystem: sparse, compression, metadata, CoW và nhiều yếu tố khác. Block size không phải số byte cấp phát chính xác của từng file.

**Câu 9.** Unit test chạy trên Linux và CI chạy trên filesystem ảo có thể có kết quả getBlockSize khác nhau không?

**Đáp án:** Có. Đây là khác biệt provider được hợp đồng cho phép. Unit test nên dùng synthetic FileStore, còn integration test nên kiểm tra cả nhánh supported/unsupported mà không chốt giá trị cố định.

**Câu 10.** Nếu ứng dụng chỉ hiển thị block size trong dashboard, xử lý UnsupportedOperationException thế nào?

**Đáp án:** Hiển thị “N/A/unsupported” hoặc trạng thái tương đương; giữ thông tin còn lại. Không nhất thiết làm toàn bộ dashboard lỗi.

**Câu 11.** Nếu thuật toán bắt buộc biết block size, có nên fallback 4096 khi unsupported không?

**Đáp án:** Không. Phải từ chối thao tác với lý do rõ ràng hoặc có một thuật toán độc lập không cần metadata. Không tạo số đo giả.

**Câu 12.** Có được coi `IOException` của getBlockSize là dấu hiệu vĩnh viễn không hỗ trợ không?

**Đáp án:** Không. IOException là lỗi thực thi truy vấn, có thể cần chẩn đoán hoặc retry theo policy; UnsupportedOperationException biểu thị thiếu khả năng theo hợp đồng.

## 19. Tài liệu tham khảo chính thức còn hiệu lực

- [Java SE 25 — FileStore.getBlockSize()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/FileStore.html#getBlockSize()): giá trị block size, yêu cầu implementation mặc định ném UnsupportedOperationException, IOException và Since 10.
- [Java SE 25 — FileStore.getAttribute(String)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/FileStore.html#getAttribute(java.lang.String)): attribute provider-specific, UnsupportedOperationException khi view/attribute không hỗ trợ và IOException.
- [Java SE 25 — FileStore.supportsFileAttributeView](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/FileStore.html#supportsFileAttributeView(java.lang.String)): kiểm tra file attribute view, không phải getBlockSize.
- [Java SE 25 — FileStore.getFileStoreAttributeView](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/FileStore.html#getFileStoreAttributeView(java.lang.Class)): trả một FileStoreAttributeView hoặc null khi không khả dụng.
- [Java SE 25 — Files.getFileStore(Path)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Files.html#getFileStore(java.nio.file.Path)): tìm FileStore chứa một đường dẫn.
- [Java SE 25 — UnsupportedOperationException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/UnsupportedOperationException.html): unchecked exception thể hiện một operation không được hỗ trợ.
- [Java SE 25 — OptionalLong](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/OptionalLong.html): biểu diễn có/không có giá trị long không cần sentinel.
- [Java SE 25 — FileAttributeView và FileStoreAttributeView](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/attribute/package-summary.html): phân biệt metadata của file với metadata của storage.

**Kết luận:** `UnsupportedOperationException` từ `FileStore.getBlockSize()` hoặc `getAttribute(...)` có thể chỉ nghĩa là provider **không cung cấp metadata được hỏi**. Thiết kế Java 10+ đúng phải **phân biệt unsupported với IOException**, không suy ra block size từ khả năng khác, và dùng fallback rõ ràng theo hợp đồng ứng dụng. Khi nào cần giá trị thật, hãy đọc từ provider hỗ trợ; khi không có, hãy báo **unknown**, không tự bịa một con số.
