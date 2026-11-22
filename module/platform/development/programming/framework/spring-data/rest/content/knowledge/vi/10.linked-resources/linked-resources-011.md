# Ảnh hưởng của phía sở hữu quan hệ và transaction khi cập nhật liên kết

## Mục tiêu

Khi client thay đổi association qua Spring Data REST, việc gửi đúng URI đến association resource mới chỉ là một phần của thao tác. Với JPA, phía sở hữu quan hệ (owning side) quyết định thay đổi nào được ghi vào khóa ngoại hoặc bảng liên kết. Transaction quyết định các thay đổi liên quan được commit cùng nhau hay có thể để lại trạng thái không nhất quán.

Vì vậy, khi thiết kế association endpoint, cần xác định property nào là owning side, cập nhật đúng phía đó và bảo đảm các thay đổi của hai đầu quan hệ nằm trong cùng transaction.

## Phía sở hữu và phía nghịch đảo trong JPA

Trong quan hệ hai chiều, JPA phân biệt:

- **Owning side:** phía khai báo mapping ghi quan hệ vào database, thường là phía có `@JoinColumn` hoặc khai báo join table. Thay đổi ở phía này quyết định khóa ngoại hoặc bản ghi liên kết được cập nhật.
- **Inverse side:** phía khai báo `mappedBy` để trỏ đến property ở owning side. Phía này giúp điều hướng quan hệ trong object model, nhưng không quyết định cập nhật khóa ngoại.

Quy tắc thường gặp:

| Loại quan hệ | Phía thường sở hữu |
| --- | --- |
| `@ManyToOne` / `@OneToMany` hai chiều | Phía `@ManyToOne` sở hữu khóa ngoại; `@OneToMany(mappedBy = ...)` là phía nghịch đảo |
| `@OneToOne` hai chiều | Phía khai báo `@JoinColumn` sở hữu |
| `@ManyToMany` hai chiều | Phía khai báo `@JoinTable`; phía còn lại dùng `mappedBy` |

Không xác định owning side bằng cách nhìn entity nào là cha trong nghiệp vụ. Hãy đọc mapping JPA: `mappedBy` chỉ ra property mà phía nghịch đảo tham chiếu.

## Ví dụ: Person và Address

Giả sử một người có nhiều địa chỉ và mỗi địa chỉ thuộc về một người. Khóa ngoại `person_id` nằm ở bảng `address`, nên `Address.person` là owning side:

    @Entity
    public class Person {
        @Id
        private Long id;

        @OneToMany(mappedBy = "person")
        private List<Address> addresses = new ArrayList<>();

        public void addAddress(Address address) {
            addresses.add(address);
            address.setPerson(this);
        }

        public void removeAddress(Address address) {
            addresses.remove(address);
            address.setPerson(null);
        }
    }

    @Entity
    public class Address {
        @Id
        private Long id;

        @ManyToOne(fetch = FetchType.LAZY)
        @JoinColumn(name = "person_id")
        private Person person;

        public void setPerson(Person person) {
            this.person = person;
        }
    }

`Person.addresses` là phía nghịch đảo vì có `mappedBy = "person"`. `Address.person` sở hữu quan hệ vì nó khai báo `@JoinColumn(name = "person_id")`.

Khi gán địa chỉ cho người, chỉ thêm vào `person.getAddresses()` là chưa đủ để yêu cầu JPA cập nhật `person_id`. Phải đặt `address.setPerson(person)` ở phía sở hữu. Helper `addAddress` cập nhật cả hai phía để object graph trong bộ nhớ nhất quán.

Tương tự, khi bỏ một địa chỉ khỏi quan hệ, cần cập nhật `Address.person` theo đúng quy tắc nghiệp vụ. Nếu chỉ xóa phần tử khỏi collection nghịch đảo, khóa ngoại có thể vẫn giữ giá trị cũ trong database.

## Association resource của Spring Data REST liên quan thế nào?

Spring Data REST công bố association dựa trên các quan hệ mà repository và mapping cho phép truy cập. Client nên lấy URL association từ `href` trong `_links`, thay vì tự ghép URL.

Ví dụ, representation của `/people/1` có thể chứa link đến association `addresses`. Client có thể gửi danh sách URI theo định dạng `text/uri-list` đến link đó:

    PUT /api/people/1/addresses HTTP/1.1
    Content-Type: text/uri-list

    http://localhost:8080/api/addresses/10
    http://localhost:8080/api/addresses/11

Request này thể hiện các địa chỉ mà client muốn liên kết với người đó. Tuy nhiên, kết quả lưu trong database vẫn phụ thuộc owning side của mapping. Nếu association endpoint thay đổi property nghịch đảo `Person.addresses` mà không cập nhật `Address.person`, JPA có thể không ghi các khóa ngoại như client mong đợi.

Với quan hệ hai chiều, hãy bảo đảm logic phía server cập nhật owning side. Có thể đặt logic đồng bộ hai đầu trong các helper method của entity và gọi chúng từ service hoặc custom endpoint. Nếu cần can thiệp vào vòng đời association của Spring Data REST, có thể dùng các event handler phù hợp như `BeforeLinkSaveEvent` để áp dụng quy tắc nghiệp vụ trước khi lưu. Không giả định rằng việc thay collection ở phía nghịch đảo sẽ tự động đồng bộ property còn lại.

## Cập nhật quan hệ trong cùng transaction

Khi thay đổi association, thường có ít nhất hai thao tác logic: tải các entity liên quan và cập nhật các property cần thiết. Nếu ứng dụng phải đồng bộ hai đầu quan hệ, các thay đổi đó nên nằm trong cùng transaction.

Ví dụ service cập nhật quan hệ trên owning side `Address.person`:

    @Service
    public class PersonAddressService {
        private final PersonRepository personRepository;
        private final AddressRepository addressRepository;

        public PersonAddressService(
                PersonRepository personRepository,
                AddressRepository addressRepository) {
            this.personRepository = personRepository;
            this.addressRepository = addressRepository;
        }

        @Transactional
        public void assignAddress(Long personId, Long addressId) {
            Person person = personRepository.findById(personId)
                    .orElseThrow();
            Address address = addressRepository.findById(addressId)
                    .orElseThrow();

            person.addAddress(address);
            // Address.person là owning side.
            addressRepository.save(address);
        }
    }

Trong transaction này, entity được tải và thay đổi trong cùng một đơn vị công việc. JPA ghi thay đổi khi flush hoặc commit. Với entity đang được quản lý trong persistence context, dirty checking có thể tự phát hiện thay đổi; gọi `save` trên repository của owning side thể hiện rõ entity nào mang mapping quyết định quan hệ.

Nếu transaction thất bại trước khi commit, các thay đổi trong transaction được rollback theo cơ chế transaction của ứng dụng. Điều này giúp tránh trường hợp một đầu quan hệ đã được lưu nhưng đầu còn lại chưa được cập nhật.

## Transaction khi gọi association endpoint

Spring Data REST thực hiện thao tác thông qua repository và cấu hình transaction của ứng dụng. Các thao tác repository có transaction theo cấu hình Spring Data; custom repository method hoặc service có thể cần khai báo transaction rõ ràng.

Không nên xem nhiều HTTP request liên tiếp là một transaction chung. Ví dụ, một request `PUT` thay đổi liên kết và một request `POST` khác cập nhật dữ liệu liên quan thường là hai đơn vị xử lý riêng. Nếu nghiệp vụ yêu cầu tất cả thay đổi cùng thành công hoặc cùng rollback, gom chúng vào một service method `@Transactional` và cung cấp một endpoint nghiệp vụ phù hợp.

Transaction cũng không tự sửa sai owning side. `@Transactional` bảo đảm ranh giới commit/rollback cho các thay đổi được thực hiện; nó không làm cho việc chỉ sửa property `mappedBy` trở thành một cập nhật khóa ngoại hợp lệ.

## Cascade và orphan removal

Cascade và owning side giải quyết hai vấn đề khác nhau:

- `cascade = ...` quyết định thao tác persistence có được truyền từ entity này sang entity liên quan hay không.
- Owning side quyết định property nào điều khiển quan hệ trong database.
- `orphanRemoval = true` có thể khiến entity con bị xóa khi nó bị loại khỏi quan hệ theo mapping phù hợp.

Thêm cascade không thay thế việc cập nhật owning side. Trước khi dùng `orphanRemoval`, hãy xác định rõ ý nghĩa nghiệp vụ của việc bỏ một liên kết: chỉ bỏ liên kết hay xóa luôn entity con. Với quan hệ dùng chung, xóa orphan không phù hợp có thể làm mất dữ liệu mà resource khác vẫn cần.

## Đồng thời cập nhật và optimistic locking

Hai client có thể cùng đọc một resource rồi cập nhật association dựa trên trạng thái cũ. Nếu cả hai ghi lại collection, lần ghi sau có thể làm mất thay đổi của lần ghi trước.

Có thể dùng `@Version` trên entity để bật optimistic locking:

    @Version
    private Long version;

Khi hai transaction cập nhật cùng một phiên bản, transaction dùng dữ liệu cũ có thể gặp lỗi optimistic locking thay vì âm thầm ghi đè. Client cần xử lý conflict bằng cách đọc lại representation mới nhất, kiểm tra các liên kết hiện tại và gửi lại thay đổi phù hợp. Nếu API dùng ETag/conditional request, client cũng nên gửi validator theo hợp đồng của endpoint.

## Quy trình cập nhật association an toàn

1. Đọc representation HAL của resource nguồn và lấy `href` của association.
2. Xác định mapping JPA để biết property nào là owning side và property nào có `mappedBy`.
3. Gửi request association với URI đúng định dạng, hoặc gọi service nghiệp vụ nếu cần đồng bộ nhiều property.
4. Trong cùng transaction, cập nhật owning side và giữ hai phía của quan hệ nhất quán trong object model.
5. Lưu entity sở hữu quan hệ khi cần; để JPA flush và commit transaction.
6. Đọc lại association hoặc resource để xác nhận trạng thái đã lưu.
7. Xử lý lỗi transaction, validation hoặc optimistic locking bằng cách đọc trạng thái mới nhất trước khi thử lại.

Điểm quyết định là mapping JPA và ranh giới transaction của ứng dụng. Association URI cho biết client muốn liên kết resource nào; owning side xác định thay đổi quan hệ được ghi vào database, còn transaction bảo đảm các thay đổi liên quan được commit hoặc rollback cùng nhau.