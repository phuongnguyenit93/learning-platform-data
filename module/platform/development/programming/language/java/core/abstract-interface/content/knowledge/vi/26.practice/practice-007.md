# Xây dựng kho dữ liệu generic với nhiều cách lưu trữ

Một **kho dữ liệu (repository)** cung cấp API để lưu, tìm, liệt kê và xóa đối tượng. Với **generic** trong Java, cùng một hợp đồng có thể dùng cho nhiều kiểu dữ liệu mà vẫn giữ kiểm tra kiểu lúc biên dịch. Kết hợp interface với nhiều implementation giúp ứng dụng chọn cách lưu trữ mà không phải viết lại logic nghiệp vụ.

Bài thực hành xây dựng hợp đồng `Repository<ID, T>` với hai backend:

- **In-memory:** dùng `Map` giữ dữ liệu trong bộ nhớ của tiến trình.
- **File-backed:** ghi bản đồ dữ liệu xuống tệp và nạp lại khi tạo repository mới.

Phần gọi sử dụng `Repository<String, Book>`, nên có thể chuyển giữa các backend mà không đổi kiểu API mà ứng dụng nhìn thấy.

## 1. Thiết kế hợp đồng generic

Một repository thường cần hai tham số kiểu:

- `T`: kiểu đối tượng được lưu, ví dụ `Book`.
- `ID`: kiểu khóa để tìm một đối tượng, ví dụ `String` hoặc `UUID`.

Nếu viết riêng `BookRepository`, `CustomerRepository` và `OrderRepository`, các thao tác cơ bản có thể bị lặp lại. Interface generic gom chúng vào một hợp đồng:

~~~java
interface Repository<ID, T> {
    void save(T entity) throws IOException;
    Optional<T> findById(ID id);
    List<T> findAll();
    boolean deleteById(ID id) throws IOException;
}
~~~

Đây là trích đoạn để minh họa hợp đồng; chương trình đầy đủ ở phần 5 bao gồm tất cả import và implementation cần thiết.

- `save` thêm hoặc thay thế đối tượng có cùng ID.
- `findById` trả về `Optional<T>`: có giá trị khi tìm thấy, rỗng khi không có.
- `findAll` trả về danh sách kết quả.
- `deleteById` trả về `true` nếu có đối tượng bị xóa, ngược lại trả về `false`.

Hợp đồng khai báo `IOException` cho thao tác ghi vì backend tệp có thể gặp lỗi. Implementation in-memory không cần ném ngoại lệ này, nhưng vẫn dùng được cùng API. Interface che giấu khác biệt triển khai trong khi vẫn thể hiện loại lỗi mà bên gọi cần xử lý.

## 2. Xác định khóa và giữ đúng kiểu

Một kho dùng `Map<ID, T>` cần biết ID của từng đối tượng. Ví dụ nhận một `Function<T, ID>` ở constructor:

~~~java
Function<Book, String> idExtractor = Book::id;
~~~

`Book::id` là method reference đến accessor của record. Repository gọi hàm này để lấy khóa mà không cần biết cấu trúc cụ thể của `Book`.

Cách này cho phép tái sử dụng repository cho nhiều loại đối tượng nếu bên gọi cung cấp hàm trích xuất ID thích hợp. ID nên không null và ổn định khi đối tượng được lưu. Nếu ID thay đổi sau khi lưu, thao tác tìm hoặc xóa bằng ID mới có thể không tìm thấy mục cũ.

## 3. Backend in-memory

`InMemoryRepository<ID, T>` dùng `LinkedHashMap<ID, T>`. Khóa là ID, giá trị là đối tượng; lưu ID đã tồn tại thay thế giá trị cũ, và `LinkedHashMap` giữ thứ tự chèn khi liệt kê. Dữ liệu mất khi tiến trình kết thúc hoặc repository bị loại bỏ.

Đây là lựa chọn hữu ích cho dữ liệu tạm thời, cache đơn giản, bài tập và kiểm thử. Nó không cung cấp độ bền qua lần chạy chương trình.

## 4. Backend file-backed

`FileRepository<ID, T>` giữ một `Map` trong bộ nhớ khi đang chạy và ghi bản đồ xuống tệp sau mỗi lần lưu hoặc xóa. Khi tạo instance mới, repository nạp bản đồ từ tệp.

Vì ví dụ dùng Java Object Serialization, cả ID và đối tượng phải triển khai `Serializable`. Đây là ràng buộc của implementation lưu tệp, không phải yêu cầu của interface generic nói chung. Backend khác có thể dùng JSON, cơ sở dữ liệu quan hệ hoặc dịch vụ từ xa với những ràng buộc riêng.

Ví dụ ghi ra tệp tạm rồi chuyển vào vị trí đích để giảm nguy cơ để lại tệp dữ liệu dở dang nếu bước ghi thất bại. Mã demo chỉ dành cho tệp đáng tin cậy của ứng dụng: **không dùng `ObjectInputStream` để giải tuần tự tệp do người dùng không tin cậy cung cấp**. Object serialization còn ràng buộc định dạng dữ liệu với các lớp Java, nên không mặc nhiên là lựa chọn tốt cho lưu trữ lâu dài.

## 5. Chương trình Java 17+ hoàn chỉnh

Lưu toàn bộ mã sau vào **GenericRepositoryDemo.java**. Chương trình khai báo hợp đồng, hai implementation và kiểu dữ liệu minh họa trong cùng một tệp để dễ chạy thử.

~~~java
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;

interface Repository<ID, T> {
    void save(T entity) throws IOException;
    Optional<T> findById(ID id);
    List<T> findAll();
    boolean deleteById(ID id) throws IOException;
}

final class InMemoryRepository<ID, T> implements Repository<ID, T> {
    private final Map<ID, T> data = new LinkedHashMap<>();
    private final Function<T, ID> idExtractor;

    InMemoryRepository(Function<T, ID> idExtractor) {
        this.idExtractor = Objects.requireNonNull(idExtractor, "idExtractor");
    }

    @Override
    public synchronized void save(T entity) {
        Objects.requireNonNull(entity, "entity");
        ID id = Objects.requireNonNull(idExtractor.apply(entity), "entity id");
        data.put(id, entity);
    }

    @Override
    public synchronized Optional<T> findById(ID id) {
        return Optional.ofNullable(data.get(Objects.requireNonNull(id, "id")));
    }

    @Override
    public synchronized List<T> findAll() {
        return List.copyOf(data.values());
    }

    @Override
    public synchronized boolean deleteById(ID id) {
        return data.remove(Objects.requireNonNull(id, "id")) != null;
    }
}

final class FileRepository<ID extends Serializable, T extends Serializable>
        implements Repository<ID, T> {
    private final Path file;
    private final Function<T, ID> idExtractor;
    private final Map<ID, T> data;

    FileRepository(Path file, Function<T, ID> idExtractor) throws IOException {
        this.file = Objects.requireNonNull(file, "file");
        this.idExtractor = Objects.requireNonNull(idExtractor, "idExtractor");
        this.data = load();
    }

    @Override
    public synchronized void save(T entity) throws IOException {
        Objects.requireNonNull(entity, "entity");
        ID id = Objects.requireNonNull(idExtractor.apply(entity), "entity id");
        data.put(id, entity);
        persist();
    }

    @Override
    public synchronized Optional<T> findById(ID id) {
        return Optional.ofNullable(data.get(Objects.requireNonNull(id, "id")));
    }

    @Override
    public synchronized List<T> findAll() {
        return List.copyOf(data.values());
    }

    @Override
    public synchronized boolean deleteById(ID id) throws IOException {
        boolean removed = data.remove(Objects.requireNonNull(id, "id")) != null;
        if (removed) {
            persist();
        }
        return removed;
    }

    @SuppressWarnings("unchecked")
    private Map<ID, T> load() throws IOException {
        if (!Files.exists(file)) {
            return new LinkedHashMap<>();
        }

        try (ObjectInputStream input =
                     new ObjectInputStream(Files.newInputStream(file))) {
            Object stored;
            try {
                stored = input.readObject();
            } catch (ClassNotFoundException ex) {
                throw new IOException("Stored class is unavailable", ex);
            }

            if (!(stored instanceof Map<?, ?> storedMap)) {
                throw new IOException("Unexpected repository file format");
            }

            Map<ID, T> result = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : storedMap.entrySet()) {
                result.put((ID) entry.getKey(), (T) entry.getValue());
            }
            return result;
        }
    }

    private void persist() throws IOException {
        Path absolute = file.toAbsolutePath();
        Path parent = absolute.getParent();
        Files.createDirectories(parent);
        Path temporary = Files.createTempFile(parent, "repo-", ".tmp");

        try {
            try (ObjectOutputStream output =
                         new ObjectOutputStream(Files.newOutputStream(temporary))) {
                output.writeObject(data);
            }

            try {
                Files.move(temporary, absolute,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ex) {
                Files.move(temporary, absolute,
                        StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}

record Book(String id, String title) implements Serializable {}

public class GenericRepositoryDemo {
    public static void main(String[] args) throws IOException {
        Repository<String, Book> memory = new InMemoryRepository<>(Book::id);
        memory.save(new Book("b1", "Java"));
        System.out.println("Memory: " + memory.findById("b1").orElseThrow());

        Path file = Files.createTempFile("books-", ".bin");
        Files.deleteIfExists(file);

        try {
            Repository<String, Book> disk = new FileRepository<>(file, Book::id);
            disk.save(new Book("b2", "Generics"));

            Repository<String, Book> reopened =
                    new FileRepository<>(file, Book::id);
            System.out.println("File: " + reopened.findById("b2").orElseThrow());
            System.out.println("Count after reopen: " + reopened.findAll().size());

            System.out.println("Deleted b2: " + reopened.deleteById("b2"));
            Repository<String, Book> afterDelete =
                    new FileRepository<>(file, Book::id);
            System.out.println("Count after delete: " + afterDelete.findAll().size());
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac GenericRepositoryDemo.java
java GenericRepositoryDemo
~~~

Stdout chính xác:

~~~text
Memory: Book[id=b1, title=Java]
File: Book[id=b2, title=Generics]
Count after reopen: 1
Deleted b2: true
Count after delete: 0
~~~

Dòng `Count after reopen: 1` cho thấy dữ liệu được đọc lại từ tệp khi tạo repository mới. Sau khi xóa `b2`, một instance mới đọc được số lượng bằng 0, xác nhận thay đổi đã được ghi xuống tệp.

## 6. Generic và interface tách trách nhiệm ra sao?

Ứng dụng khai báo biến theo interface:

~~~java
Repository<String, Book> repository =
        new InMemoryRepository<>(Book::id);
~~~

Nếu cần backend lưu tệp, có thể khởi tạo bằng implementation khác:

~~~java
Repository<String, Book> repository =
        new FileRepository<>(path, Book::id);
~~~

Hai đoạn trên minh họa cùng kiểu hợp đồng; trong một chương trình chỉ khai báo biến `repository` một lần và khởi tạo bằng backend được chọn. Phần nghiệp vụ tiếp tục gọi `save`, `findById` hoặc `findAll` mà không cần phụ thuộc trực tiếp vào lớp cụ thể.

Ba ý thiết kế quan trọng:

1. **Generic giữ an toàn kiểu.** `Repository<String, Book>` dùng `Book` làm dữ liệu và `String` làm khóa; trình biên dịch phát hiện nhiều trường hợp truyền nhầm kiểu.
2. **Interface định nghĩa hợp đồng.** Cả hai implementation cung cấp cùng thao tác nhưng dùng cơ chế lưu khác nhau.
3. **Dependency được chọn ở ranh giới khởi tạo.** Có thể truyền repository vào service qua constructor để logic nghiệp vụ không tự tạo hoặc phụ thuộc cứng vào backend.

Generic không tự tạo ra tính bền dữ liệu, đồng bộ giữa nhiều tiến trình hay giao dịch. Những thuộc tính đó phụ thuộc vào backend và hợp đồng cụ thể.

## 7. So sánh và giới hạn

| Tiêu chí | In-memory | File-backed trong ví dụ |
|---|---|---|
| Giữ dữ liệu sau khi tiến trình dừng | Không | Có, trong tệp đã ghi |
| Chi phí thao tác thông thường | Thường thấp | Có thêm I/O khi ghi |
| Yêu cầu kiểu dữ liệu | Không cần `Serializable` | ID và T phải `Serializable` |
| Chia sẻ giữa nhiều tiến trình | Không | Không được đồng bộ giữa nhiều instance |
| Phù hợp | Cache, dữ liệu tạm, test | Demo, dữ liệu nhỏ và tệp đáng tin cậy |

Implementation file-backed này nạp toàn bộ dữ liệu vào bộ nhớ lúc khởi tạo rồi ghi lại bản đồ sau mỗi thay đổi. Trong ví dụ, `save`/`deleteById` thay đổi `Map` trước khi ghi tệp; nếu `persist()` ném `IOException`, trạng thái bộ nhớ có thể đã đổi dù thao tác báo lỗi. Ứng dụng thật cần chính sách khôi phục/rollback hoặc cập nhật theo bản sao rồi chỉ công bố trạng thái sau khi lưu thành công. Hai instance cùng mở một tệp không tự đồng bộ trạng thái; các thao tác đồng thời từ nhiều tiến trình cũng không được khóa hoặc điều phối. Ứng dụng thực cần nhiều người ghi, dữ liệu lớn, truy vấn, giao dịch hoặc phục hồi lỗi nên cân nhắc cơ sở dữ liệu hay backend chuyên dụng.

Các kiểm tra nên có khi phát triển repository:

- Lưu hai đối tượng có cùng ID phải thay thế đúng đối tượng cũ.
- Tìm ID chưa tồn tại phải trả về `Optional.empty()`.
- Xóa ID chưa tồn tại phải trả về `false`.
- ID và đối tượng null phải được xử lý nhất quán.
- Lỗi đọc/ghi phải được chuyển lên nơi có thể quyết định retry, báo lỗi hoặc khôi phục.
- Kiểm tra file không hợp lệ, phiên bản lớp thay đổi và quyền truy cập tệp.
- Nếu cần dùng đồng thời, xác định chính sách đồng bộ và tính nhất quán thay vì giả định `synchronized` trên từng instance bảo vệ được một tệp dùng chung.

## 8. Lỗi thường gặp

- **Gắn kiểu cụ thể vào hợp đồng generic.** Nếu interface khai báo trực tiếp `Book`, nó khó dùng cho kiểu khác. Đặt tham số kiểu ở vị trí cần tổng quát hóa.
- **Dùng `Object` thay cho generic.** Cách này làm mất kiểm tra kiểu và thường buộc bên gọi ép kiểu.
- **Không xác định quy tắc ID.** Repository cần cách nhất quán để lấy khóa; ID null hoặc thay đổi sẽ làm tra cứu khó dự đoán.
- **Cho rằng mọi backend có cùng hành vi.** Cùng interface không có nghĩa là cùng độ trễ, độ bền, giao dịch hoặc giới hạn đồng thời.
- **Bỏ qua lỗi I/O.** Lưu xuống tệp có thể thất bại do quyền, dung lượng hoặc lỗi hệ thống. Không nên báo thành công khi dữ liệu chưa được ghi.
- **Giải tuần tự dữ liệu không đáng tin cậy.** Java native serialization không phù hợp để đọc tùy tiện dữ liệu không tin cậy; chọn định dạng và cơ chế kiểm tra an toàn phù hợp.
- **Để logic nghiệp vụ phụ thuộc implementation cụ thể.** Nếu service gọi trực tiếp chi tiết riêng của `FileRepository`, việc thay backend sẽ khó hơn và lợi ích của interface bị giảm.

## 9. Quy trình thực hành

1. Xác định kiểu dữ liệu `T`, kiểu khóa `ID` và thao tác tối thiểu mà nghiệp vụ cần.
2. Khai báo `Repository<ID, T>` bằng kiểu trả về rõ nghĩa như `Optional<T>` và `List<T>`.
3. Viết implementation đơn giản trước, chẳng hạn `InMemoryRepository`, để kiểm tra hợp đồng.
4. Thêm backend khác mà không đổi cách phần nghiệp vụ gọi interface.
5. Kiểm thử cùng bộ hành vi trên từng implementation, rồi kiểm tra riêng các thuộc tính đặc thù như độ bền, lỗi I/O và đồng thời.
6. Chọn backend theo yêu cầu thực tế về vòng đời dữ liệu, quy mô, truy vấn, vận hành và phục hồi.

Một repository generic tái sử dụng cùng hợp đồng cho nhiều kiểu dữ liệu; các implementation cung cấp cách lưu cụ thể. Khi tách hai trách nhiệm này rõ ràng, ứng dụng dễ thử nghiệm, dễ thay backend và giữ logic nghiệp vụ ít phụ thuộc vào chi tiết lưu trữ hơn.
