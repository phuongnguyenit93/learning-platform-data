# CoroutineCrudRepository và CoroutineSortingRepository

## 1. Mục tiêu và phạm vi

Trong chương **Kotlin và coroutine** của module **Spring Data Commons**, bài này hướng dẫn khai báo repository theo kiểu Kotlin coroutine để thực hiện CRUD và sắp xếp dữ liệu.

Sau bài học, bạn cần làm được các việc sau:

- Kết hợp đúng hai interface CRUD và sorting.
- Chọn giữa hàm `suspend`, giá trị nullable và `Flow`.
- Gọi repository từ service mà không dùng `runBlocking` để chờ I/O.
- Thu thập Flow đúng thời điểm và hiểu tác động của việc thu thập lại.
- Giữ rõ khả năng truy vấn, transaction và kiểm soát cạnh tranh của store.
- Kiểm tra dữ liệu sau lưu, trường hợp không tìm thấy và kết quả của Flow.

Ví dụ chính dùng R2DBC để lưu sách. Các abstraction repository thuộc Commons; kết nối, mapping và thực thi truy vấn thuộc mô-đun lưu trữ.

## 2. Điều kiện để repository coroutine hoạt động

Các import cần nhận diện:

~~~kotlin
import org.springframework.data.repository.kotlin.CoroutineCrudRepository
import org.springframework.data.repository.kotlin.CoroutineSortingRepository
~~~

Repository coroutine được xây trên hạ tầng repository reactive của mô-đun hỗ trợ. Thêm một interface vào classpath không tự biến mọi driver hoặc repository đồng bộ thành đường truy cập non-blocking.

Cần có:

- Mô-đun và driver reactive phù hợp với store đã chọn.
- Hạ tầng mapping, repository scanning và kết nối.
- Kotlin cùng các thư viện coroutine tương thích.
- Các cầu nối `kotlinx-coroutines-core`, `kotlinx-coroutines-reactive`, `kotlinx-coroutines-reactor` theo yêu cầu tích hợp.

Tài liệu Commons cũng lưu ý repository coroutine được nhận diện khi kế thừa `CoroutineCrudRepository`. Ví dụ trong bài giữ interface này trong cây kế thừa.

Xem [Spring Data Commons: Coroutines](https://docs.spring.io/spring-data/commons/reference/kotlin/coroutines.html).

Ví dụ R2DBC cần driver R2DBC, không chỉ một JDBC datasource. Nếu một lời gọi JDBC blocking được đặt trong hàm `suspend`, từ khóa đó không làm driver đổi cơ chế I/O.

## 3. Kết hợp CRUD và sorting tường minh

Repository có cả hai nhóm chức năng:

~~~kotlin
interface BookRepository :
    CoroutineCrudRepository<Book, Long>,
    CoroutineSortingRepository<Book, Long>
~~~

`Book` là domain type; `Long` là kiểu id dùng khi truy vấn.

Từ Spring Data 3.0, sorting repository không còn tự kế thừa CRUD repository tương ứng. Vì vậy, chỉ extends `CoroutineSortingRepository` không cung cấp toàn bộ các method `save`, `findById` hoặc `deleteById`.

Xem [Spring Data Commons: Defining Repository Interfaces](https://docs.spring.io/spring-data/commons/reference/repositories/definition.html).

Khi nhiều repository cùng dùng tổ hợp này, có thể tạo base interface:

~~~kotlin
import org.springframework.data.repository.NoRepositoryBean
import org.springframework.data.repository.kotlin.CoroutineCrudRepository
import org.springframework.data.repository.kotlin.CoroutineSortingRepository

@NoRepositoryBean
interface CoroutineCrudAndSortRepository<T : Any, ID : Any> :
    CoroutineCrudRepository<T, ID>,
    CoroutineSortingRepository<T, ID>
~~~

Sau đó repository cụ thể kế thừa base này:

~~~kotlin
interface BookRepository :
    CoroutineCrudAndSortRepository<Book, Long>
~~~

Chỉ chọn một cách khai báo BookRepository. `@NoRepositoryBean` dành cho base còn tham số generic, ngăn việc tạo một repository bean chưa có domain type cụ thể.

Không ghép thêm `CrudRepository` đồng bộ vào cùng interface chỉ để có CRUD. Cách kết hợp đó có thể tạo các method cùng tên nhưng hợp đồng thực thi và kiểu trả về không tương thích.

## 4. suspend, nullable và Flow diễn đạt những gì?

### 4.1. suspend nhận một kết quả mà không cần tự subscribe

~~~kotlin
suspend fun load(id: Long): Book?
~~~

Caller phải ở một ngữ cảnh cho phép gọi hàm suspending. Hàm có thể tạm dừng trong lúc chờ kết quả mà không giữ thread chỉ để chờ theo cách blocking, nếu đường I/O bên dưới hỗ trợ điều đó.

`suspend` không tự khởi tạo một thread, không tự chạy song song và không bảo đảm thân hàm hoàn toàn non-blocking. Một đoạn xử lý blocking được gọi bên trong vẫn cần được nhận diện và xử lý theo thiết kế của ứng dụng.

### 4.2. Nullable biểu đạt nhánh không có dữ liệu

`findById` trả `T?`. Với BookRepository, caller nhận `Book?`:

~~~kotlin
val book: Book? = books.findById(id)
~~~

Không tìm thấy có thể là kết quả `null` hợp lệ. Lỗi kết nối lại là exception; không nên gom hai tình huống thành một.

### 4.3. Flow biểu đạt nhiều kết quả

~~~kotlin
fun activeBooks(): Flow<Book>
~~~

Hàm có thể trả về một Flow ngay, còn dữ liệu được lấy khi caller tương tác với Flow, thường qua terminal operator như `collect` hoặc `toList`.

Với hình dạng này, không cần thêm `suspend` chỉ để trả một Flow. Caller vẫn cần coroutine khi thực hiện terminal operator suspending.

Một bảng đối chiếu về ý nghĩa:

| Reactive | Coroutine tương ứng về kết quả |
| --- | --- |
| `Mono<T>` có thể rỗng | `suspend fun ...: T?` |
| `Mono<T>` bắt buộc có giá trị | `suspend fun ...: T` |
| `Mono<Void>` | `suspend fun ...: Unit` |
| `Flux<T>` | `fun ...: Flow<T>` |

Bảng là cách đọc hợp đồng, không phải chỉ dẫn đổi tên mọi method một cách máy móc. Chữ ký repository và khả năng của mô-đun vẫn quyết định cách dùng thực tế.

## 5. Các method CRUD cần nắm

Các chữ ký tiêu biểu của `CoroutineCrudRepository<T, ID>`:

| Method | Kết quả và cách thực thi |
| --- | --- |
| `suspend fun <S : T> save(entity: S): T` | Một entity sau lưu |
| `fun <S : T> saveAll(entities: Iterable<S>): Flow<S>` | Luồng entity sau lưu |
| `fun <S : T> saveAll(entityStream: Flow<S>): Flow<S>` | Nhận nguồn Flow để lưu |
| `suspend fun findById(id: ID): T?` | Entity hoặc null |
| `suspend fun existsById(id: ID): Boolean` | Có hoặc không tồn tại |
| `fun findAll(): Flow<T>` | Luồng entity |
| `fun findAllById(ids: Iterable<ID>): Flow<T>` | Các entity tìm thấy |
| `suspend fun count(): Long` | Số lượng |
| `suspend fun deleteById(id: ID)` | Hoàn tất không trả dữ liệu |
| `suspend fun delete(entity: T)` | Xóa entity theo hợp đồng store |

Xem [CoroutineCrudRepository, nhánh 3.5.x](https://github.com/spring-projects/spring-data-commons/blob/3.5.x/src/main/kotlin/org/springframework/data/repository/kotlin/CoroutineCrudRepository.kt).

Một chi tiết dễ nhầm là chữ ký `save` ở đây trả về `T`, còn `saveAll` giữ kiểu phần tử `S` trong Flow. Không sao chép giả định về generic từ một CRUD interface khác.

Luôn dùng kết quả trả về từ `save` cho bước tiếp theo. Store có thể trả một instance đã có id, version hoặc metadata mới.

Các overload khác cần được tra theo phiên bản đang dùng. Đặc biệt:

- `findAllById` không hứa giữ thứ tự id đầu vào và có thể thiếu các id không tồn tại.
- `deleteById` không trả số dòng xóa; một id không tìm thấy không mặc nhiên là lỗi.
- Lỗi optimistic locking phụ thuộc việc model và store có áp dụng version tương ứng.

## 6. Ví dụ R2DBC: model và repository

### 6.1. Model bất biến

~~~kotlin
package com.example.coroutinebooks

import org.springframework.data.annotation.Id
import org.springframework.data.annotation.Version
import org.springframework.data.relational.core.mapping.Table

@Table("books")
data class Book(
    @field:Id
    val id: Long? = null,
    val sku: String,
    val title: String,
    val active: Boolean = true,
    @field:Version
    val version: Long? = null
)
~~~

`id` nullable cho phép biểu diễn entity mới chưa được database cấp id. Điều này khác với kiểu id của repository: các lời gọi tìm theo id vẫn dùng `Long`.

`version` phục vụ optimistic locking trong đường lưu R2DBC được cấu hình phù hợp. Khi dùng `copy` để sửa title, cần giữ id và version hiện tại.

### 6.2. Schema minh họa

Với PostgreSQL, một schema tương ứng có thể là:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    title VARCHAR(200) NOT NULL,
    active BOOLEAN NOT NULL,
    version BIGINT
);
~~~

Đây là SQL cho ví dụ PostgreSQL, không phải schema dùng nguyên vẹn cho mọi database. Ứng dụng vẫn cần cơ chế tạo schema và cấu hình R2DBC riêng.

Ràng buộc unique cho `sku` nằm ở database để giữ tính duy nhất ngay cả khi nhiều request tạo sách đồng thời.

### 6.3. Repository cụ thể

~~~kotlin
package com.example.coroutinebooks

import kotlinx.coroutines.flow.Flow
import org.springframework.data.domain.Sort
import org.springframework.data.repository.kotlin.CoroutineCrudRepository
import org.springframework.data.repository.kotlin.CoroutineSortingRepository

interface BookRepository :
    CoroutineCrudRepository<Book, Long>,
    CoroutineSortingRepository<Book, Long> {

    suspend fun findBySku(sku: String): Book?

    fun findByActive(
        active: Boolean,
        sort: Sort
    ): Flow<Book>
}
~~~

`findBySku` dùng nullable cho trường hợp không tìm thấy. Schema giữ sku duy nhất, phù hợp kỳ vọng tối đa một kết quả.

`findByActive` là derived query nhận Sort của ví dụ R2DBC. Không cần tự viết implementation nếu query method được mô-đun hỗ trợ.

Ứng dụng cần ConnectionFactory, entity template và repository scanning tương ứng. Tài liệu [Spring Data Relational: Coroutines](https://docs.spring.io/spring-data/relational/reference/kotlin/coroutines.html) mô tả cơ chế tích hợp coroutine trên hạ tầng reactive.

## 7. Service gọi repository theo cách tuần tự

~~~kotlin
package com.example.coroutinebooks

import kotlinx.coroutines.flow.Flow
import org.springframework.data.domain.Sort
import org.springframework.stereotype.Service

class BookNotFound(id: Long) :
    RuntimeException("Book not found: $id")

@Service
class BookService(
    private val books: BookRepository
) {

    suspend fun create(
        sku: String,
        title: String
    ): Book {
        val normalizedSku = sku.trim()
        val normalizedTitle = title.trim()

        require(normalizedSku.isNotEmpty()) {
            "sku must not be blank"
        }
        require(normalizedTitle.isNotEmpty()) {
            "title must not be blank"
        }

        return books.save(
            Book(
                sku = normalizedSku,
                title = normalizedTitle
            )
        )
    }

    suspend fun requireBook(id: Long): Book =
        books.findById(id) ?: throw BookNotFound(id)

    suspend fun rename(
        id: Long,
        nextTitle: String
    ): Book {
        val normalizedTitle = nextTitle.trim()
        require(normalizedTitle.isNotEmpty()) {
            "title must not be blank"
        }

        val current = requireBook(id)

        return books.save(
            current.copy(title = normalizedTitle)
        )
    }

    fun activeBooks(): Flow<Book> =
        books.findByActive(
            true,
            Sort.by(
                Sort.Order.asc("title"),
                Sort.Order.asc("id")
            )
        )

    suspend fun removeIfPresent(id: Long) {
        books.deleteById(id)
    }
}
~~~

Các lời gọi `suspend` trong `rename` được viết tuần tự: đọc xong mới tạo bản sao và lưu. Không cần `subscribe`, `block` hoặc một lần `launch` riêng để thực hiện từng thao tác.

Caller nhận entity sau lưu, bao gồm version được cập nhật nếu store áp dụng version. Không trả ngay bản `copy` chưa xác nhận lưu.

`requireBook` chuyển một nhánh null hợp lệ ở tầng repository thành lỗi nghiệp vụ của service. Không dùng `!!` để tạo một lỗi thiếu ngữ nghĩa.

Không cần kiểm tra `existsBySku` trước mỗi insert chỉ để thay cho ràng buộc unique. Hai request vẫn có thể cùng nhìn thấy kết quả “chưa có”; database constraint mới là nơi giữ quy tắc trong ví dụ.

## 8. Flow chỉ thực hiện công việc khi được thu thập theo nguồn đó

### 8.1. Trả Flow chưa phải đã lấy dữ liệu

Trong một hàm suspending:

~~~kotlin
val stream = service.activeBooks()
~~~

Dòng này nhận một Flow. Để dùng dữ liệu:

~~~kotlin
import kotlinx.coroutines.flow.collect

stream.collect { book ->
    println(book.title)
}
~~~

Hoặc, với tập kết quả đã được giới hạn phù hợp:

~~~kotlin
import kotlinx.coroutines.flow.toList

val result: List<Book> = stream.toList()
~~~

`toList` giữ toàn bộ phần tử đã thu thập trong bộ nhớ. Không dùng nó vô điều kiện cho một tập dữ liệu rất lớn hoặc nguồn không kết thúc.

Flow hỗ trợ phối hợp nhịp xử lý bằng suspension. Tuy nhiên, chi phí database, buffering và việc ứng dụng tự gom dữ liệu vẫn cần được xem xét.

Xem [Kotlin: Flow API](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-core/kotlinx.coroutines.flow/-flow/).

### 8.2. save và saveAll có hình dạng thực thi khác nhau

~~~kotlin
val saved: Book = books.save(newBook)
~~~

Đây là lời gọi suspending lấy kết quả lưu. Không cần collect cho kết quả Book.

Trong khi đó:

~~~kotlin
val savedStream: Flow<Book> =
    books.saveAll(newBooks)
~~~

Caller đang nhận một Flow. Để chờ toàn bộ thao tác từ nguồn này:

~~~kotlin
savedStream.collect { savedBook ->
    println(savedBook.id)
}
~~~

Nếu không cần xử lý từng kết quả, vẫn cần terminal operation để thực thi và chờ nguồn hoàn tất theo hợp đồng của nó.

### 8.3. Thu thập lại có thể thực hiện lại công việc

Với nguồn repository cold thông thường, collect lại có thể thực thi lại truy vấn hoặc thao tác ghi. Không coi một biến Flow như một List đã lấy sẵn dữ liệu.

Đặc biệt, collect lại một nguồn `saveAll` chứa entity mới chưa có id có thể gây một lượt ghi khác hoặc lỗi unique, tùy dữ liệu và store.

Bản thân kiểu `Flow` không khẳng định mọi nguồn đều cold. `SharedFlow`, `StateFlow` hoặc nguồn được chia sẻ có vòng đời khác. Cần hiểu nguồn cụ thể đang dùng.

### 8.4. map có thể gọi hàm suspend

Một lựa chọn xử lý tập ứng viên đã có:

~~~kotlin
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.asFlow
import kotlinx.coroutines.flow.map

val savedInSequence: Flow<Book> =
    candidates.asFlow()
        .map { book ->
            books.save(book)
        }
~~~

`candidates` là một tập Book hữu hạn. Lambda của Flow map cho phép gọi hàm suspending, nên không cần đổi sang một chuỗi Mono chỉ để lưu một phần tử.

Đây là một phương án thay cho đường lưu nhiều phần tử khác, không phải bước cần chạy thêm sau `saveAll`. Theo cách ghép tuần tự này, nó chưa tạo một transaction chung cho toàn bộ tập.

## 9. CoroutineSortingRepository cung cấp sorting, không tự cung cấp Page

Hợp đồng chính là:

~~~kotlin
fun findAll(sort: Sort): Flow<T>
~~~

Xem [CoroutineSortingRepository, nhánh 3.5.x](https://github.com/spring-projects/spring-data-commons/blob/3.5.x/src/main/kotlin/org/springframework/data/repository/kotlin/CoroutineSortingRepository.kt).

Ví dụ:

~~~kotlin
val ordered: Flow<Book> = books.findAll(
    Sort.by(
        Sort.Order.asc("title"),
        Sort.Order.asc("id")
    )
)
~~~

Dùng tên property của model cho Sort. Store chịu trách nhiệm mapping và thực thi việc sắp xếp.

Tiêu chí id phụ giúp phân biệt các sách cùng title. Nó không biến dữ liệu đang thay đổi thành một snapshot cố định qua nhiều request.

### 9.1. Phân biệt sorting ở store với sorting sau khi đọc

~~~kotlin
val sortedInMemory =
    books.findAll()
        .toList()
        .sortedBy { it.title }
~~~

Đoạn này đọc và gom dữ liệu rồi mới sắp xếp tại ứng dụng. Nó khác về nơi thực thi và chi phí so với `books.findAll(sort)`.

### 9.2. take không phải hợp đồng giới hạn query tại database

~~~kotlin
import kotlinx.coroutines.flow.take

val firstTwenty =
    books.findAll(sort).take(20)
~~~

`take` giới hạn phần tử được thu thập tiếp và có thể hủy upstream khi đủ. Không suy ra query database chắc chắn đã được chuyển thành một limit tối ưu.

Nếu cần query giới hạn hoặc phân trang, dùng query method hoặc API mà mô-đun và phiên bản đang dùng hỗ trợ.

### 9.3. Không có sẵn findAll(Pageable) từ sorting interface

Chỉ extends `CoroutineSortingRepository` không tự cung cấp một `Page<Book>`, tổng số trang hoặc một overload `findAll(Pageable)`.

Muốn trả dữ liệu trang và tổng số lượng, cần thiết kế thêm cách lấy dữ liệu, count và quy tắc nhất quán. Hai lần đọc riêng có thể quan sát trạng thái khác nhau nếu dữ liệu đang thay đổi.

## 10. Coroutine không tự tạo transaction nghiệp vụ

Hai lần gọi `save` liên tiếp có thể là hai thao tác riêng nếu không có transaction phù hợp.

Với R2DBC và một `TransactionalOperator` đã được tạo từ đúng reactive transaction manager, có thể dùng extension `executeAndAwait`:

~~~kotlin
import org.springframework.transaction.reactive.TransactionalOperator
import org.springframework.transaction.reactive.executeAndAwait

class BookBatchService(
    private val books: BookRepository,
    private val operator: TransactionalOperator
) {

    suspend fun deactivateBoth(
        firstId: Long,
        secondId: Long
    ) {
        require(firstId != secondId)

        operator.executeAndAwait {
            val first = books.findById(firstId)
                ?: throw BookNotFound(firstId)
            val second = books.findById(secondId)
                ?: throw BookNotFound(secondId)

            books.save(first.copy(active = false))
            books.save(second.copy(active = false))
            Unit
        }
    }
}
~~~

Ví dụ cần được dùng như một thành phần đã inject đúng repository và operator. Để quản lý cùng transaction R2DBC, manager và hai thao tác phải dùng cùng hạ tầng tài nguyên phù hợp.

Không bắt exception rồi trả thành công ngay trong block nếu chính sách yêu cầu rollback. Đồng thời, phải kiểm tra kết quả với database thật để chứng minh cả hai thay đổi cùng commit hoặc rollback.

Spring có các extension transaction cho hàm suspending và Flow. Xem [Spring Framework: Coroutines and Transactions](https://docs.spring.io/spring-framework/reference/languages/kotlin/coroutines.html#coroutines.transactions).

Transaction không thay thế optimistic locking hoặc quy tắc isolation. Nó cũng không tự bao phủ một lời gọi HTTP hay một store khác.

Nếu chọn transaction bằng annotation thay cho operator, cần kiểm tra hạ tầng proxy, manager, hỗ trợ coroutine và quy tắc mở class/method của cấu hình Kotlin. Không mặc định một annotation trên bất kỳ object nào cũng được thực thi.

## 11. Giữ vòng đời coroutine và lỗi rõ ràng

### 11.1. Không dùng runBlocking để nối service suspend

Một service coroutine nên gọi trực tiếp repository suspending. `runBlocking` giữ thread chờ hoàn tất và không phải cầu nối cần thêm vào giữa các hàm `suspend`.

Tương tự, `Dispatchers.IO` không phải yêu cầu mặc định cho một repository đã dùng driver reactive. Thay dispatcher cũng không thay đổi bản chất của một driver blocking.

### 11.2. Không tách công việc ghi ra khỏi caller ngoài ý muốn

Nếu service dùng một scope toàn cục để `launch` việc lưu rồi trả về, caller có thể không chờ được kết quả lưu hoặc không nhận đúng lỗi.

Giữ công việc trong vòng đời request hoặc scope do ứng dụng quản lý phù hợp. Nếu cần song song hóa, phải xác định tài nguyên, giới hạn concurrency và cách caller chờ các tác vụ.

Viết hai lời gọi `suspend` nối tiếp không tự làm chúng chạy đồng thời. Ngược lại, tạo thêm coroutine cũng không tự làm nhiều lệnh database cùng connection trở nên hợp lệ.

### 11.3. Không đổi mọi exception thành null

Một mẫu dễ che lỗi:

~~~kotlin
suspend fun findQuietly(id: Long): Book? =
    runCatching {
        books.findById(id)
    }.getOrNull()
~~~

Lỗi kết nối hoặc cancellation có thể bị nhìn như không có sách. Chỉ chuyển đổi lỗi theo loại và hợp đồng rõ ràng.

Khi tự viết catch rộng trong coroutine, cần giữ ngữ nghĩa cancellation thay vì nuốt `CancellationException` rồi tiếp tục coi tác vụ thành công.

### 11.4. Thu thập Flow phải diễn ra trong phạm vi cần thiết

Một transaction hoặc security context có thể phụ thuộc ngữ cảnh thực thi. Không tự tạo một scope tách rời để collect Flow rồi mặc định nó giữ toàn bộ ngữ cảnh caller.

Đặc biệt, một hàm tạo Flow xong rồi kết thúc chưa có nghĩa mọi công việc của Flow đã được thực hiện trong khoảng thời gian hàm đó chạy.

## 12. Kiểm tra repository bằng runTest và readback

Các ví dụ kiểm tra dùng `kotlinx-coroutines-test` cùng thư viện assertion Kotlin và JUnit phù hợp. `runTest` tạo môi trường chạy coroutine cho test; nó không biến I/O database thật thành thời gian ảo.

Xem [Kotlin: runTest API](https://kotlinlang.org/api/kotlinx.coroutines/kotlinx-coroutines-test/kotlinx.coroutines.test/run-test.html).

Snippet sau đặt trong test class đã được cấu hình inject một BookRepository thật cho database kiểm tra:

~~~kotlin
import java.util.UUID
import kotlinx.coroutines.test.runTest
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import org.junit.jupiter.api.Test

@Test
fun savesReadsAndDeletesBook() = runTest {
    val saved = books.save(
        Book(
            sku = "test-" + UUID.randomUUID(),
            title = "Coroutine repositories"
        )
    )
    val id = assertNotNull(saved.id)

    try {
        val reloaded = assertNotNull(
            books.findById(id)
        )

        assertEquals(saved.sku, reloaded.sku)
        assertEquals(
            "Coroutine repositories",
            reloaded.title
        )
    } finally {
        books.deleteById(id)
    }

    assertNull(books.findById(id))
}
~~~

Test chứng minh kết quả lưu có id, đọc lại đúng dữ liệu và id đã xóa cho nhánh null. Nó không dựa vào object đầu vào để kết luận việc lưu thành công.

Một test kiểm tra Flow cần thực sự thu thập nguồn:

~~~kotlin
import kotlinx.coroutines.flow.toList

val actual = books.findByActive(
    true,
    Sort.by(
        Sort.Order.asc("title"),
        Sort.Order.asc("id")
    )
).toList()
~~~

Để assert danh sách chính xác, dùng fixture và phạm vi dữ liệu test được cô lập; đừng dựa vào mọi sách trong một database dùng chung.

Các tình huống cần kiểm tra theo yêu cầu ứng dụng:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Id không tồn tại | `findById` trả null |
| Lưu entity mới | Dùng instance trả về để lấy id/version |
| Sku đã tồn tại | Ràng buộc unique tạo lỗi phù hợp |
| Chỉ tạo Flow mà chưa collect | Không coi đó là thao tác đã hoàn tất |
| Collect Flow ghi nhiều lần | Hiểu và kiểm soát tác động thực thi lại |
| Nhiều title trùng nhau | Sort có tiêu chí phụ theo yêu cầu |
| Phiên bản đã cũ | Optimistic locking được store áp dụng |
| Lần ghi sau trong transaction thất bại | Lần ghi trước không giữ thay đổi của transaction lỗi |
| Coroutine bị hủy | Caller và tài nguyên phản ứng theo đúng hợp đồng |

Mock repository hữu ích cho logic null/error của service, nhưng không chứng minh factory đã nhận diện repository coroutine hoặc query chạy đúng trên store.

## 13. Lỗi thường gặp và bài thực hành

| Hiện tượng | Điểm cần kiểm tra |
| --- | --- |
| Không tạo được repository bean | Mô-đun hỗ trợ, dependency coroutine, scanner và cây kế thừa |
| Thiếu method save | Chỉ kế thừa sorting |
| Gọi save từ hàm thường bị lỗi biên dịch | Chưa ở hàm suspend hoặc coroutine phù hợp |
| SaveAll không tạo dữ liệu như mong đợi | Nguồn Flow có được collect và chờ hoàn tất không |
| Null gây lỗi khó hiểu | Caller dùng `!!` thay cho xử lý nhánh không tìm thấy |
| Tốn nhiều bộ nhớ | Gom toàn bộ bằng `toList` hoặc sort sau khi đọc hết |
| Service trả trước khi ghi xong | Tác vụ bị tách bằng scope hoặc launch không được chờ |
| Lỗi database bị nhìn thành không có dữ liệu | Catch quá rộng hoặc `getOrNull` che lỗi |
| Không có Page hay tổng số trang | Nhầm sorting repository với API phân trang đầy đủ |
| Có hai lần ghi nhưng chỉ một lần rollback | Thiếu transaction chung hoặc sai tài nguyên |

Thực hành hoàn thiện một repository sách:

1. Tạo model có id và một mã nghiệp vụ duy nhất.
2. Khai báo repository có cả CRUD và sorting.
3. Viết hàm tạo, tìm bắt buộc có dữ liệu và đổi tên bằng `suspend`.
4. Trả `Flow` cho truy vấn nhiều dòng có sorting.
5. Kiểm tra sự khác biệt giữa tạo Flow và collect.
6. Đọc lại dữ liệu sau lưu bằng id trả về.
7. Kiểm tra transaction cho một đơn vị công việc gồm nhiều lần ghi.
8. Giải thích khả năng và giới hạn của store đã chọn.

Bài thực hành đạt yêu cầu khi bạn phân biệt được **hàm suspending trả kết quả**, **Flow chờ thu thập**, **nhánh nullable**, **sorting tại store** và **ranh giới transaction**, đồng thời dùng readback để chứng minh dữ liệu thực sự được lưu.
