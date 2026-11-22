# Vai trò của PagingAndSortingRepository và thay đổi quan hệ kế thừa theo phiên bản

Trong Spring Data, **PagingAndSortingRepository** là hợp đồng repository dành cho việc đọc dữ liệu có phân trang và sắp xếp. Nó thuộc Spring Data Commons nên có thể được dùng với nhiều module lưu trữ như JPA, MongoDB, JDBC hoặc Redis, tùy khả năng mà module tương ứng hỗ trợ.

Với Spring Data REST, kiểu repository mà ứng dụng khai báo ảnh hưởng đến những thao tác mà lớp REST có thể phát hiện và công bố. Vì vậy, thay đổi quan hệ kế thừa của PagingAndSortingRepository từ Spring Data 3.0 là điểm cần kiểm tra khi nâng cấp ứng dụng.

## 1. PagingAndSortingRepository cung cấp những gì?

Interface này bổ sung hai cách truy vấn tập hợp:

- \`findAll(Pageable pageable)\`: lấy một trang dữ liệu. Kết quả là \`Page<T>\`, chứa nội dung trang cùng thông tin như số trang hiện tại, kích thước trang, tổng số phần tử và tổng số trang.
- \`findAll(Sort sort)\`: lấy các phần tử đã được sắp xếp theo một hoặc nhiều thuộc tính. Kết quả là \`Iterable<T>\`; phương thức này không cung cấp metadata tổng số trang.

\`Pageable\` mô tả trang cần lấy, thường gồm chỉ số trang, kích thước trang và có thể cả thứ tự sắp xếp. \`Sort\` mô tả thứ tự sắp xếp mà không yêu cầu chia kết quả thành trang.

Ví dụ, một lời gọi repository có thể yêu cầu trang đầu tiên gồm 20 bản ghi, sắp xếp theo họ tên tăng dần. Repository implementation của từng module sẽ chuyển yêu cầu đó thành truy vấn phù hợp với hệ quản trị dữ liệu.

Interface này chỉ định nghĩa khả năng phân trang và sắp xếp ở tầng repository. Nó không tự định nghĩa truy vấn nghiệp vụ riêng; ứng dụng vẫn có thể bổ sung query method, derived query hoặc truy vấn tùy chỉnh theo module đang dùng.

## 2. Quan hệ kế thừa trước và từ Spring Data 3.0

Đây là thay đổi quan trọng nhất cần nhớ khi đọc hoặc nâng cấp repository.

### Spring Data 2.x trở về trước

Trong các phiên bản trước Spring Data 3.0, PagingAndSortingRepository kế thừa CrudRepository:

~~~java
PagingAndSortingRepository<T, ID>
        extends CrudRepository<T, ID>
        extends Repository<T, ID>
~~~

Do đó, chỉ cần khai báo:

~~~java
public interface PersonRepository
        extends PagingAndSortingRepository<Person, Long> {
}
~~~

repository đã có cả hai nhóm khả năng:

- CRUD từ CrudRepository, chẳng hạn \`save\`, \`findById\`, \`findAll()\`, \`deleteById\`.
- Phân trang và sắp xếp từ PagingAndSortingRepository, chẳng hạn \`findAll(Pageable)\` và \`findAll(Sort)\`.

Một số mã nguồn cũ vì vậy chỉ khai báo PagingAndSortingRepository nhưng vẫn gọi được các phương thức CRUD.

### Từ Spring Data 3.0 trở đi

Kể từ Spring Data 3.0, PagingAndSortingRepository **không còn kế thừa CrudRepository**. Hai interface cùng kế thừa Repository và biểu diễn hai nhóm khả năng riêng:

~~~java
CrudRepository<T, ID>
        extends Repository<T, ID>

PagingAndSortingRepository<T, ID>
        extends Repository<T, ID>
~~~

Nếu ứng dụng cần cả CRUD lẫn phân trang/sắp xếp, hãy khai báo rõ cả hai:

~~~java
public interface PersonRepository
        extends CrudRepository<Person, Long>,
                PagingAndSortingRepository<Person, Long> {
}
~~~

Nếu chỉ cần phân trang và sắp xếp, có thể tiếp tục chỉ kế thừa PagingAndSortingRepository. Khi đó repository không tự có các phương thức CRUD được định nghĩa bởi CrudRepository.

Trong Spring Data JPA, nếu cần bộ thao tác repository JPA thông dụng cùng CRUD, phân trang và sắp xếp, JpaRepository thường là lựa chọn tiện lợi vì nó kết hợp các hợp đồng cần thiết cho trường hợp này.

## 3. Tác động đến Spring Data REST

Spring Data REST dựa trên metadata và các phương thức của repository để tạo tài nguyên REST. Các thao tác repository được công bố sẽ được ánh xạ thành các thao tác HTTP tương ứng, tùy cấu hình export và các annotation áp dụng.

### Phân trang và sắp xếp trên collection resource

Khi repository cung cấp khả năng phân trang/sắp xếp, client có thể yêu cầu dữ liệu qua các tham số truy vấn quen thuộc:

~~~http
GET /people?page=0&size=20&sort=lastName,asc
~~~

Ý nghĩa:

- \`page=0\`: yêu cầu trang đầu tiên theo cách đánh số trang mặc định.
- \`size=20\`: yêu cầu tối đa 20 phần tử trong trang.
- \`sort=lastName,asc\`: sắp xếp theo thuộc tính \`lastName\` tăng dần. Có thể truyền nhiều tiêu chí sort theo cú pháp mà Pageable/Spring Data REST hỗ trợ.

Với kết quả kiểu Page, phản hồi REST có thể chứa metadata về trang và các liên kết điều hướng như trang trước, trang tiếp theo hoặc trang cuối. Hình dạng JSON/HAL cụ thể phụ thuộc cấu hình và phiên bản Spring Data REST.

### Thay đổi CRUD khi nâng cấp lên Spring Data 3.0

Giả sử repository cũ chỉ khai báo:

~~~java
public interface PersonRepository
        extends PagingAndSortingRepository<Person, Long> {
}
~~~

Ở Spring Data 2.x, repository này đồng thời kế thừa CrudRepository nên các thao tác CRUD có sẵn.

Sau khi nâng cấp lên Spring Data 3.0+, repository chỉ còn hợp đồng phân trang/sắp xếp. Những chỗ trong mã Java gọi \`save\`, \`deleteById\`, \`findById\` hoặc \`findAll()\` từ CrudRepository sẽ không còn được thỏa mãn bởi interface này. Tập thao tác CRUD mà Spring Data REST có thể phát hiện từ repository cũng có thể thay đổi theo.

Nếu API cần tiếp tục hỗ trợ cả đọc trang, sắp xếp và CRUD, hãy bổ sung CrudRepository vào khai báo repository. Việc thêm interface cần phản ánh đúng nhu cầu nghiệp vụ và khả năng của module lưu trữ.

Lưu ý: kế thừa interface không đồng nghĩa mọi phương thức luôn được công bố công khai. Spring Data REST còn chịu ảnh hưởng từ cấu hình export, \`@RepositoryRestResource\`, \`@RestResource(exported = false)\` và các tùy chỉnh repository khác.

## 4. Ví dụ chọn interface

### Chỉ cần phân trang và sắp xếp

~~~java
public interface ReadOnlyPersonRepository
        extends PagingAndSortingRepository<Person, Long> {
}
~~~

Cách khai báo này phù hợp khi hợp đồng repository chỉ cần truy vấn collection theo trang hoặc thứ tự sắp xếp. Nó không cung cấp CRUD thông qua CrudRepository.

### Cần cả CRUD và phân trang/sắp xếp

~~~java
public interface PersonRepository
        extends CrudRepository<Person, Long>,
                PagingAndSortingRepository<Person, Long> {
}
~~~

Đây là cách khai báo tường minh, phù hợp với Spring Data 3.0+ khi ứng dụng muốn giữ cả hai nhóm khả năng.

### Ứng dụng Spring Data JPA

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

JpaRepository phù hợp khi ứng dụng dùng JPA và cần API repository phong phú hơn, bao gồm CRUD, phân trang và sắp xếp. Với module khác, hãy chọn interface tương ứng do module đó cung cấp.

## 5. Cấu hình kích thước trang trong Spring Data REST

Ứng dụng Spring Boot có thể đặt kích thước trang mặc định và giới hạn kích thước tối đa cho Spring Data REST. Ví dụ:

~~~yaml
spring:
  data:
    rest:
      default-page-size: 20
      max-page-size: 100
~~~

Các con số trên chỉ là giá trị cấu hình minh họa. Hãy chọn giới hạn phù hợp với dung lượng phản hồi, chi phí truy vấn và nhu cầu client. Việc đặt giới hạn tối đa giúp tránh request yêu cầu một trang quá lớn.

## 6. Checklist khi nâng cấp từ Spring Data 2.x lên 3.x

1. Tìm các repository chỉ khai báo \`PagingAndSortingRepository\`.
2. Kiểm tra nơi sử dụng những phương thức CRUD như \`save\`, \`delete\`, \`findById\` và \`findAll()\`.
3. Nếu repository vẫn cần CRUD, bổ sung \`CrudRepository\` hoặc dùng interface chuyên biệt của module như \`JpaRepository\` khi phù hợp.
4. Nếu repository chỉ cần phân trang/sắp xếp, giữ hợp đồng PagingAndSortingRepository và không phụ thuộc vào các phương thức CRUD được kế thừa trước đây.
5. Kiểm tra lại API Spring Data REST: collection GET có phân trang/sắp xếp theo nhu cầu hay không, và các thao tác tạo, cập nhật, xóa còn được công bố đúng như thiết kế hay không.
6. Kiểm tra cấu hình page size, max page size và các annotation điều khiển việc export repository/phương thức.

## 7. Những điểm cần ghi nhớ

- PagingAndSortingRepository cung cấp \`findAll(Pageable)\` và \`findAll(Sort)\`.
- Trước Spring Data 3.0, PagingAndSortingRepository kế thừa CrudRepository nên có cả CRUD.
- Từ Spring Data 3.0, hai interface tách biệt và cùng kế thừa Repository.
- Muốn giữ CRUD cùng phân trang/sắp xếp trên Spring Data 3.0+, hãy kế thừa cả CrudRepository và PagingAndSortingRepository, hoặc dùng interface cấp cao hơn của module phù hợp.
- Trong Spring Data REST, thay đổi hợp đồng repository có thể làm thay đổi các thao tác được công bố. Cần kiểm tra cả phương thức Java lẫn API HTTP sau khi nâng cấp.
